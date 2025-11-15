#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Tuple

ROOT = Path(os.getenv('TRUST_GUARD_ROOT') or Path(__file__).resolve().parents[2])

POLICY_FILE = ROOT / 'policy' / 'trust_guard_policy.json'
STATE_DIR = ROOT / 'state'
STATE_FILE = STATE_DIR / 'trust_lock_state.json'
LOG_FILE = STATE_DIR / 'trust_lock_log.jsonl'
AUDIT_FILE = ROOT / 'audit_summary.md'

INTEGRITY_REGISTRY = ROOT / 'exports' / 'integrity_metrics_registry.csv'
WEIGHTED_CONSENSUS = ROOT / 'federation' / 'weighted_consensus.json'
REPUTATION_INDEX = ROOT / 'federation' / 'reputation_index.json'
OVERRIDE_STATE = ROOT / 'state' / 'override_state.json'


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


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
            POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(POLICY_FILE, defaults)
            return defaults
        with POLICY_FILE.open('r', encoding='utf-8') as f:
            loaded = json.load(f)
        # Merge defaults
        for k, v in defaults.items():
            if k not in loaded:
                loaded[k] = v
        for k, v in defaults['thresholds'].items():
            loaded['thresholds'][k] = loaded['thresholds'].get(k, v)
        return loaded
    except Exception:
        return defaults


def read_integrity_score() -> float | None:
    if not INTEGRITY_REGISTRY.exists():
        return None
    try:
        with INTEGRITY_REGISTRY.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return None
            # Assume last row latest; field 'integrity'
            last = rows[-1]
            for key in ['integrity', 'score', 'integrity_score']:
                if key in last:
                    try:
                        return float(last[key])
                    except ValueError:
                        continue
            return None
    except Exception:
        return None


def read_weighted_consensus() -> float | None:
    if not WEIGHTED_CONSENSUS.exists():
        return None
    try:
        data = json.loads(WEIGHTED_CONSENSUS.read_text(encoding='utf-8'))
        return float(data.get('weighted_agreement_pct')) if data.get('weighted_agreement_pct') is not None else None
    except Exception:
        return None


def read_reputation_index() -> float | None:
    if not REPUTATION_INDEX.exists():
        return None
    try:
        data = json.loads(REPUTATION_INDEX.read_text(encoding='utf-8'))
        # support either top-level score or mean
        if 'score' in data:
            return float(data['score'])
        if 'mean_score' in data:
            return float(data['mean_score'])
        return None
    except Exception:
        return None


def read_override_active() -> bool:
    try:
        if not OVERRIDE_STATE.exists():
            return False
        st = json.loads(OVERRIDE_STATE.read_text(encoding='utf-8'))
        return bool(st.get('active'))
    except Exception:
        return False


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


def evaluate(policy: dict[str, Any]) -> Tuple[dict[str, float], bool, str]:
    metrics = {
        'integrity': read_integrity_score() or 0.0,
        'consensus': read_weighted_consensus() or 0.0,
        'reputation': read_reputation_index() or 0.0,
    }
    thr = policy['thresholds']
    breaches = []
    if metrics['integrity'] < thr['integrity']:
        breaches.append('integrity')
    if metrics['consensus'] < thr['weighted_consensus']:
        breaches.append('consensus')
    if metrics['reputation'] < thr['reputation_index']:
        breaches.append('reputation')
    if not breaches:
        return metrics, False, 'none'
    reason = 'multiple' if len(breaches) > 1 else breaches[0]
    return metrics, True, reason


def with_retries(fn, *args, **kwargs):
    delays = [1, 3, 9]
    last_exc = None
    for i, d in enumerate(delays):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            time.sleep(d)
    if last_exc:
        raise last_exc


def create_fix_branch(prefix: str, note: str) -> None:
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
    branch = f"fix/trust-guard-{ts}" if prefix == 'trust-guard' else f"fix/lock-fs-{ts}"
    diag_dir = ROOT / 'diagnostics'
    diag_dir.mkdir(parents=True, exist_ok=True)
    log_path = diag_dir / f"trust_guard_failure_{ts}.log"
    log_path.write_text(note, encoding='utf-8')
    # Append marker
    idempotent_audit_marker(f"<!-- TRUST_GUARD: FIX_BRANCH_CREATED {utc_now_iso()} branch: {branch} -->")
    # Create branch if git available
    try:
        subprocess.run(['git', 'checkout', '-b', branch], cwd=str(ROOT), check=False)
        subprocess.run(['git', 'add', str(log_path), str(AUDIT_FILE)], cwd=str(ROOT), check=False)
        subprocess.run(['git', 'commit', '-m', 'fix(trust-guard): capture failure artifacts'], cwd=str(ROOT), check=False)
        subprocess.run(['git', 'push', 'origin', branch], cwd=str(ROOT), check=False)
    except Exception:
        pass


def persist_state(state: dict[str, Any]) -> None:
    with_retries(atomic_write_json, STATE_FILE, state)
    with_retries(atomic_append_jsonl, LOG_FILE, state | {'event': 'state_update'})


def enforce(policy: dict[str, Any]) -> dict[str, Any]:
    metrics, breached, reason = evaluate(policy)
    now = utc_now()
    override_active = read_override_active()

    # Load existing state
    current: dict[str, Any] = {}
    if STATE_FILE.exists():
        try:
            current = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            current = {}

    manual_today = current.get('manual_unlocks_today', 0)
    last_reset = current.get('manual_unlocks_last_reset')
    today_str = now.date().isoformat()
    try:
        reset_date = datetime.fromisoformat(last_reset).date() if last_reset else None
    except Exception:
        reset_date = None
    if reset_date is None or reset_date < now.date():
        manual_today = 0

    state = {
        'locked': False,
        'locked_at': current.get('locked_at'),
        'reason': 'none',
        'metrics': metrics,
        'unlock_scheduled_at': None,
        'manual_unlocks_today': manual_today,
        'manual_unlocks_last_reset': today_str,
        'bypass': False,
    }

    if breached:
        # Enforce lock window
        lock_window = timedelta(minutes=policy['lock_window_minutes'])
        if current.get('locked') and current.get('locked_at'):
            try:
                locked_at = datetime.fromisoformat(current['locked_at'])
                if now < locked_at + lock_window:
                    state = current | {'metrics': metrics}
                else:
                    # Continue evaluating for auto-unlock
                    pass
            except Exception:
                pass

        # If override active, honor bypass
        if override_active:
            state['bypass'] = True
            state['locked'] = False
            state['reason'] = 'bypass'
            with_retries(atomic_append_jsonl, LOG_FILE, {'event': 'bypass', 'timestamp': utc_now_iso(), 'metrics': metrics})
            idempotent_audit_marker(f"<!-- TRUST_GUARD: UNLOCKED {utc_now_iso()} -->")
        else:
            state['locked'] = True
            state['locked_at'] = utc_now_iso()
            state['reason'] = reason
            if policy.get('auto_unlock_after_minutes'):
                state['unlock_scheduled_at'] = (now + timedelta(minutes=policy['auto_unlock_after_minutes'])).isoformat()
            with_retries(atomic_append_jsonl, LOG_FILE, {'event': 'locked', 'timestamp': utc_now_iso(), 'reason': reason, 'metrics': metrics})
            idempotent_audit_marker(f"<!-- TRUST_GUARD: LOCKED {utc_now_iso()} reason: {reason} -->")
    else:
        state['locked'] = False
        state['reason'] = 'none'
        with_retries(atomic_append_jsonl, LOG_FILE, {'event': 'unlocked', 'timestamp': utc_now_iso(), 'metrics': metrics})
        idempotent_audit_marker(f"<!-- TRUST_GUARD: UNLOCKED {utc_now_iso()} -->")

    try:
        persist_state(state)
    except Exception as e:
        idempotent_audit_marker(f"<!-- TRUST_GUARD: FS_ERROR {utc_now_iso()} -->")
        create_fix_branch('lock-fs', f"Persist state failed: {e}")
        raise
    return state


def force_unlock(policy: dict[str, Any], reason: str, actor: str | None = None) -> dict[str, Any]:
    now = utc_now()
    # Load current state
    current: dict[str, Any] = {}
    if STATE_FILE.exists():
        try:
            current = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            current = {}

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
        return {
            'status': 'limit_exceeded',
            'allowed_per_day': policy_limit,
            'manual_unlocks_today': manual_today,
        }

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

    with_retries(atomic_append_jsonl, LOG_FILE, {'event': 'manual_unlock', 'timestamp': utc_now_iso(), 'reason': reason, 'actor': actor})
    idempotent_audit_marker(f"<!-- TRUST_GUARD: MANUAL_UNLOCK {utc_now_iso()} by {actor or 'unknown'} -->")
    persist_state(state)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Multi-Layer Trust Guard Controller')
    parser.add_argument('--check', action='store_true', help='Evaluate and print JSON summary')
    parser.add_argument('--enforce', action='store_true', help='Evaluate and persist state')
    parser.add_argument('--force-unlock', action='store_true', help='Manual unlock')
    parser.add_argument('--reason', type=str, default='', help='Reason for manual unlock')
    args = parser.parse_args(argv)

    policy = load_policy()
    try:
        if args.check:
            metrics, breached, reason = evaluate(policy)
            print(json.dumps({'metrics': metrics, 'breached': breached, 'reason': reason}, indent=2))
            idempotent_audit_marker(f"<!-- TRUST_GUARD: VERIFIED {utc_now_iso()} -->")
            return 0
        elif args.enforce:
            state = enforce(policy)
            print(json.dumps(state, indent=2))
            return 0
        elif args.force_unlock:
            state = force_unlock(policy, args.reason or 'unspecified', actor=os.getenv('USER') or os.getenv('USERNAME'))
            if state.get('status') == 'limit_exceeded':
                print(json.dumps(state, indent=2))
                return 0
            print(json.dumps(state, indent=2))
            return 0
        else:
            # default: check
            metrics, breached, reason = evaluate(policy)
            print(json.dumps({'metrics': metrics, 'breached': breached, 'reason': reason}, indent=2))
            return 0
    except Exception as e:
        # Internal failure after retries
        create_fix_branch('trust-guard', f"Internal error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
