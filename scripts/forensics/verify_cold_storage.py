#!/usr/bin/env python3
"""
Phase XVII - Instruction 94: Automated Cold-Storage Verification

Recompute hashes for snapshots and mirror artifacts to confirm consistency.
Logs results to forensics/verification_log.jsonl and appends audit marker.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = ROOT / 'snapshots'
MIRRORS = ROOT / 'mirrors'
FORENSICS = ROOT / 'forensics'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def append_line(p: Path, line: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a', encoding='utf-8') as f:
        f.write(line.rstrip() + "\n")


def append_audit_marker(ts: str) -> None:
    audit = ROOT / 'audit_summary.md'
    with audit.open('a', encoding='utf-8') as f:
        f.write(f'<!-- COLD_STORAGE_VERIFY: UPDATED {ts} -->\n')


def verify():
    ts = utc_now_iso()
    # Verify snapshots via recorded hashes
    snap_hashes = SNAPSHOTS / 'ledger_snapshot_hash.json'
    snap_records = []
    if snap_hashes.exists():
        try:
            snap_records = json.loads(snap_hashes.read_text(encoding='utf-8'))
            if isinstance(snap_records, dict):
                snap_records = [snap_records]
        except Exception:
            snap_records = []
    for rec in snap_records:
        fname = rec.get('file')
        expected = rec.get('sha256')
        bundle = SNAPSHOTS / fname if fname else None
        ok = False
        if bundle and bundle.exists():
            ok = (sha256_path(bundle) == expected)
        append_line(FORENSICS / 'verification_log.jsonl', json.dumps({'timestamp': ts, 'type': 'snapshot', 'file': fname, 'ok': ok, 'verified': ok}))

    # Verify mirrors via anchor_chain.json continuity
    chain = MIRRORS / 'anchor_chain.json'
    if chain.exists():
        try:
            data = json.loads(chain.read_text(encoding='utf-8'))
        except Exception:
            data = []
        prev_chain_hash = ''
        for entry in data:
            file = MIRRORS / entry.get('file', '')
            sha = entry.get('sha256')
            chain_hash = entry.get('chain_hash')
            ok_file = file.exists() and sha256_path(file) == sha
            import hashlib as _h
            ok_chain = _h.sha256((prev_chain_hash + (sha or '')).encode('utf-8')).hexdigest() == chain_hash
            prev_chain_hash = chain_hash or ''
            verified = bool(ok_file and ok_chain)
            append_line(FORENSICS / 'verification_log.jsonl', json.dumps({'timestamp': ts, 'type': 'mirror', 'file': file.name, 'ok_file': ok_file, 'ok_chain': ok_chain, 'verified': verified}))

    append_audit_marker(ts)


def main() -> int:
    verify()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
