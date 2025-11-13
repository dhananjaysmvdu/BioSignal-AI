#!/usr/bin/env python3
"""
Phase XV - Instruction 81 & 82 (transparency extension)

README Provenance Hashing and Transparency Consistency Sweep (extended for transparency docs).

Functions:
- Hash README.md and write docs/readme_integrity.json {timestamp, sha256}
- Append audit marker <!-- README_INTEGRITY: VERIFIED <UTC ISO> --> to docs/audit_summary.md
- If README hash changed vs previous, append to logs/readme_hash_log.jsonl and
  fail (exit 2) unless a recent commit message mentions 'docs' or 'readme'.
- Hash transparency files (GOVERNANCE_TRANSPARENCY.md, INSTRUCTION_EXECUTION_SUMMARY.md, docs/audit_summary.md)
  and write docs/transparency_integrity.json with per-file entries {timestamp, sha256}.
- If any transparency hash mismatch persists for > 2 days (based on previous timestamp),
  append marker <!-- TRANSPARENCY_DRIFT: DETECTED <UTC ISO> --> to docs/audit_summary.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
LOGS = ROOT / 'logs'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def load_json(p: Path) -> Any:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None


def append_line(p: Path, line: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a', encoding='utf-8') as f:
        f.write(line.rstrip() + "\n")


def get_recent_commit_messages(n: int = 20) -> list[str]:
    try:
        out = subprocess.check_output(['git', 'log', f'-n{n}', '--pretty=%s'], cwd=str(ROOT))
        msgs = out.decode('utf-8', errors='ignore').splitlines()
        return msgs
    except Exception:
        return []


def verify_readme() -> bool:
    """Return True if README ok; False if mismatch without docs/readme commits (should fail)."""
    readme = ROOT / 'README.md'
    if not readme.exists():
        print('README.md not found; skipping', file=sys.stderr)
        return True

    now = utc_now_iso()
    sha = sha256_path(readme)
    out_json = DOCS / 'readme_integrity.json'
    prev = load_json(out_json) or {}
    prev_sha = prev.get('sha256')
    changed = (prev_sha is not None and prev_sha != sha)

    # Write current integrity json
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({'timestamp': now, 'sha256': sha}, indent=2), encoding='utf-8')

    # Append audit marker
    audit_file = DOCS / 'audit_summary.md'
    append_line(audit_file, f'<!-- README_INTEGRITY: VERIFIED {now} -->')

    # Log mismatch if changed
    if changed:
        LOGS.mkdir(parents=True, exist_ok=True)
        log_line = {
            'timestamp': now,
            'prev_sha256': prev_sha,
            'new_sha256': sha,
        }
        append_line(LOGS / 'readme_hash_log.jsonl', json.dumps(log_line))

        # Require recent commit mentioning docs or readme
        msgs = get_recent_commit_messages(30)
        ok = any(('docs' in m.lower() or 'readme' in m.lower()) for m in msgs)
        if not ok:
            print('README hash changed without docs/readme commit reference; failing.', file=sys.stderr)
            return False
    return True


def verify_transparency() -> Dict[str, Dict[str, str]]:
    files = [
        ROOT / 'GOVERNANCE_TRANSPARENCY.md',
        ROOT / 'INSTRUCTION_EXECUTION_SUMMARY.md',
        DOCS / 'audit_summary.md',
    ]
    now = utc_now_iso()
    out_path = DOCS / 'transparency_integrity.json'
    prev: Dict[str, Dict[str, str]] = load_json(out_path) or {}
    current: Dict[str, Dict[str, str]] = {}

    for fp in files:
        key = str(fp.relative_to(ROOT))
        if fp.exists():
            current[key] = {'timestamp': now, 'sha256': sha256_path(fp)}
        else:
            current[key] = {'timestamp': now, 'sha256': None}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(current, indent=2), encoding='utf-8')

    # Drift detection (> 2 days since previous record and still mismatched)
    drift_detected = False
    for key, cur in current.items():
        prev_entry = prev.get(key)
        if not prev_entry:
            continue
        prev_sha = prev_entry.get('sha256')
        cur_sha = cur.get('sha256')
        if prev_sha != cur_sha:
            try:
                prev_ts = datetime.fromisoformat(prev_entry.get('timestamp'))
            except Exception:
                prev_ts = None
            if prev_ts and (datetime.now(timezone.utc) - prev_ts) > timedelta(days=2):
                drift_detected = True

    if drift_detected:
        append_line(DOCS / 'audit_summary.md', f'<!-- TRANSPARENCY_DRIFT: DETECTED {now} -->')

    return current


def main() -> int:
    ok = verify_readme()
    verify_transparency()
    return 0 if ok else 2


if __name__ == '__main__':
    sys.exit(main())
