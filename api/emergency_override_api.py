"""Emergency Override API

Provides endpoints to activate/deactivate system-wide emergency override that places
adaptive response engine into bypass mode. All state is stored under state/ directory
with atomic writes and event logging.

Endpoints:
  POST /override/activate  (body JSON: {"reason": "<string>"})
  POST /override/deactivate
  GET  /override/status

State file: state/override_state.json
Log file:   state/override_log.jsonl

Audit markers appended to audit_summary.md:
  <!-- OVERRIDE_ACTIVATED <UTC> -->
  <!-- OVERRIDE_DEACTIVATED <UTC> -->

When activated, adaptive_response_engine.py is invoked in bypass mode via env var ADAPTIVE_BYPASS=1.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / 'state'
STATE_FILE = STATE_DIR / 'override_state.json'
LOG_FILE = STATE_DIR / 'override_log.jsonl'
AUDIT_FILE = ROOT / 'audit_summary.md'
ADAPTIVE_ENGINE = ROOT / 'scripts' / 'forensics' / 'adaptive_response_engine.py'

app = FastAPI(title="Emergency Override API", version="1.0.0")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def append_log(record: dict[str, Any]) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record)
    # Atomic append: read existing then rewrite (simpler than concurrent append for this context)
    existing = ''
    if LOG_FILE.exists():
        existing = LOG_FILE.read_text(encoding='utf-8')
    tmp = LOG_FILE.with_suffix(LOG_FILE.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        f.write(existing)
        f.write(line + '\n')
    tmp.replace(LOG_FILE)


def append_audit_marker(marker: str) -> None:
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = ''
    if AUDIT_FILE.exists():
        existing = AUDIT_FILE.read_text(encoding='utf-8')
    tmp = AUDIT_FILE.with_suffix(AUDIT_FILE.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        f.write(existing)
        f.write(marker + '\n')
    tmp.replace(AUDIT_FILE)


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"active": False}
    try:
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {"active": False, "error": "state_corrupt"}


def run_adaptive_bypass() -> None:
    if not ADAPTIVE_ENGINE.exists():
        return
    subprocess.run(
        [os.sys.executable, str(ADAPTIVE_ENGINE)],
        env={**os.environ, "ADAPTIVE_BYPASS": "1"},
        capture_output=True,
        text=True,
        timeout=30
    )


@app.post('/override/activate')
def activate_override(payload: dict[str, Any]):
    reason = payload.get('reason', '').strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Activation requires 'reason' string")
    state = {
        'active': True,
        'activated_at': utc_now_iso(),
        'reason': reason
    }
    atomic_write_json(STATE_FILE, state)
    append_log({'event': 'activate', 'timestamp': state['activated_at'], 'reason': reason})
    append_audit_marker(f"<!-- OVERRIDE_ACTIVATED {state['activated_at']} -->")
    run_adaptive_bypass()
    return JSONResponse(state)


@app.post('/override/deactivate')
def deactivate_override():
    current = load_state()
    if not current.get('active'):
        # Idempotent
        return JSONResponse(current)
    state = {
        'active': False,
        'deactivated_at': utc_now_iso(),
        'reason': current.get('reason')
    }
    atomic_write_json(STATE_FILE, state)
    append_log({'event': 'deactivate', 'timestamp': state['deactivated_at']})
    append_audit_marker(f"<!-- OVERRIDE_DEACTIVATED {state['deactivated_at']} -->")
    return JSONResponse(state)


@app.get('/override/status')
def override_status():
    return JSONResponse(load_state())


if __name__ == '__main__':
    # Simple dev server
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8001)
