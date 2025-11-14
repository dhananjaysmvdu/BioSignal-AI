"""Trust Guard API

Endpoints:
  GET /trust/status
  POST /trust/force-unlock { reason, actor }
Implements policy limits, atomic writes, audit markers, retries, and fix-branch creation on persistent failures.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

ROOT = Path(os.getenv('TRUST_GUARD_ROOT') or Path(__file__).resolve().parents[1])
STATE_DIR = ROOT / 'state'
STATE_FILE = STATE_DIR / 'trust_lock_state.json'
LOG_FILE = STATE_DIR / 'trust_lock_log.jsonl'
POLICY_FILE = ROOT / 'policy' / 'trust_guard_policy.json'
AUDIT_FILE = ROOT / 'audit_summary.md'

app = FastAPI(title='Trust Guard API', version='1.0.0')


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def atomic_append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ''
    if path.exists():
        existing = path.read_text(encoding='utf-8')
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        f.write(existing)
        f.write(json.dumps(record) + '\n')
    tmp.replace(path)


def with_retries(fn, *args, **kwargs):
    delays = [1, 3, 9]
    last_exc = None
    for d in delays:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            time.sleep(d)
    if last_exc:
        raise last_exc


def idempotent_audit_marker(marker: str) -> None:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = ''
    if AUDIT_FILE.exists():
        existing = AUDIT_FILE.read_text(encoding='utf-8')
    lines = [ln for ln in existing.splitlines() if not ln.strip().startswith('<!-- TRUST_GUARD:')]
    tmp = AUDIT_FILE.with_suffix(AUDIT_FILE.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + ('\n' if lines else ''))
        f.write(marker + '\n')
    tmp.replace(AUDIT_FILE)


def load_policy() -> dict[str, Any]:
    defaults = {
        'thresholds': {
            'integrity': 90,
            'weighted_consensus': 92,
            'reputation_index': 85,
        },
        'lock_window_minutes': 60,
        'auto_unlock_after_minutes': 1440,
        'max_manual_unlocks_per_day': 2,
    }
    try:
        if not POLICY_FILE.exists():
            atomic_write_json(POLICY_FILE, defaults)
            return defaults
        loaded = json.loads(POLICY_FILE.read_text(encoding='utf-8'))
        for k, v in defaults.items():
            if k not in loaded:
                loaded[k] = v
        for k, v in defaults['thresholds'].items():
            loaded['thresholds'][k] = loaded['thresholds'].get(k, v)
        return loaded
    except Exception:
        return defaults


@app.get('/trust/status')
def trust_status():
    if not STATE_FILE.exists():
        return JSONResponse({'locked': False, 'reason': 'none'})
    try:
        return JSONResponse(json.loads(STATE_FILE.read_text(encoding='utf-8')))
    except json.JSONDecodeError:
        return JSONResponse({'locked': False, 'error': 'state_corrupt'})


@app.post('/trust/force-unlock')
def trust_force_unlock(payload: dict[str, Any]):
    reason = (payload.get('reason') or '').strip()
    actor = (payload.get('actor') or '').strip() or 'unknown'
    if not reason:
        raise HTTPException(status_code=400, detail="Force unlock requires 'reason'")

    # Load state
    current: dict[str, Any] = {}
    if STATE_FILE.exists():
        try:
            current = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            current = {}

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    last_reset = current.get('manual_unlocks_last_reset')
    manual_today = current.get('manual_unlocks_today', 0)
    try:
        reset_date = datetime.fromisoformat(last_reset).date() if last_reset else None
    except Exception:
        reset_date = None
    if reset_date is None or reset_date < now.date():
        manual_today = 0

    policy_limit = int(load_policy().get('max_manual_unlocks_per_day', 2))
    if manual_today >= policy_limit:
        idempotent_audit_marker(f"<!-- TRUST_GUARD: UNLOCK_LIMIT_EXCEEDED {utc_now_iso()} -->")
        raise HTTPException(status_code=403, detail='Manual unlock limit exceeded for today')

    state = {
        'locked': False,
        'locked_at': None,
        'reason': 'manual',
        'metrics': current.get('metrics', {}),
        'unlock_scheduled_at': None,
        'manual_unlocks_today': manual_today + 1,
        'manual_unlocks_last_reset': today,
        'bypass': False,
    }

    try:
        with_retries(atomic_write_json, STATE_FILE, state)
        with_retries(atomic_append_jsonl, LOG_FILE, {'event': 'manual_unlock', 'timestamp': utc_now_iso(), 'reason': reason, 'actor': actor})
        idempotent_audit_marker(f"<!-- TRUST_GUARD: MANUAL_UNLOCK {utc_now_iso()} by {actor} -->")
        return JSONResponse(state)
    except Exception as e:
        idempotent_audit_marker(f"<!-- TRUST_GUARD: API_FS_ERROR {utc_now_iso()} -->")
        # Attempt fix branch creation
        try:
            ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
            branch = f"fix/trust-guard-{ts}"
            (ROOT / 'diagnostics').mkdir(parents=True, exist_ok=True)
            (ROOT / 'diagnostics' / f"trust_guard_failure_{ts}.log").write_text(f"API write failure: {e}", encoding='utf-8')
            os.system(f"git -C {ROOT} checkout -b {branch}")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail='Persistent write failure')


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8002)
