#!/usr/bin/env python3
"""
Phase XVII - Instruction 94: Automated Cold-Storage Verification

Recompute hashes for snapshots and mirror artifacts to confirm consistency.
Logs results to forensics/verification_log.jsonl and appends audit marker.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Add forensics directory to path for forensics_utils import
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forensics_utils import (
    utc_now_iso,
    compute_sha256,
    log_forensics_event,
    append_audit_marker as audit_marker,
)


def append_line(p: Path, line: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with p.open('a', encoding='utf-8') as f:
            f.write(line.rstrip() + "\n")
    except Exception:
        # Best effort fallback ignored; error logging handled separately
        pass


def verify():
    ts = utc_now_iso()
    snapshots_dir = ROOT / 'snapshots'
    mirrors_dir = ROOT / 'mirrors'
    forensics_dir = ROOT / 'forensics'
    forensics_dir.mkdir(parents=True, exist_ok=True)
    log_file = forensics_dir / 'verification_log.jsonl'

    # Verify snapshots via recorded hashes
    snap_hashes = snapshots_dir / 'ledger_snapshot_hash.json'
    try:
        if snap_hashes.exists():
            snap_records = json.loads(snap_hashes.read_text(encoding='utf-8'))
            if isinstance(snap_records, dict):
                snap_records = [snap_records]
        else:
            snap_records = []
    except Exception as e:
        log_forensics_event({'error': 'read_snapshot_hash_failed', 'exc': str(e)})
        snap_records = []
    for rec in snap_records:
        fname = rec.get('file')
        expected = rec.get('sha256')
        bundle = snapshots_dir / fname if fname else None
        ok = False
        try:
            if bundle and bundle.exists():
                sha = compute_sha256(bundle)
                ok = (sha == expected) if sha else False
        except Exception as e:
            log_forensics_event({'error': 'snapshot_verify_failed', 'file': fname, 'exc': str(e)})
        append_line(log_file, json.dumps({'timestamp': ts, 'type': 'snapshot', 'file': fname, 'ok': ok, 'verified': ok}))

    # Verify mirrors via anchor_chain.json continuity
    chain = mirrors_dir / 'anchor_chain.json'
    if chain.exists():
        try:
            data = json.loads(chain.read_text(encoding='utf-8'))
            if not isinstance(data, list):
                data = []
        except Exception as e:
            log_forensics_event({'error': 'read_anchor_chain_failed', 'exc': str(e)})
            data = []
        prev_chain_hash = ''
        for entry in data:
            file = mirrors_dir / entry.get('file', '')
            sha = entry.get('sha256')
            chain_hash = entry.get('chain_hash')
            ok_file = False
            ok_chain = False
            try:
                file_sha = compute_sha256(file) if file.exists() else None
                ok_file = file_sha == sha if file_sha else False
                import hashlib as _h
                ok_chain = _h.sha256((prev_chain_hash + (sha or '')).encode('utf-8')).hexdigest() == (chain_hash or '')
            except Exception as e:
                log_forensics_event({'error': 'mirror_verify_failed', 'file': file.name, 'exc': str(e)})
            prev_chain_hash = chain_hash or ''
            verified = bool(ok_file and ok_chain)
            append_line(log_file, json.dumps({'timestamp': ts, 'type': 'mirror', 'file': file.name, 'ok_file': ok_file, 'ok_chain': ok_chain, 'verified': verified}))
    else:
        # Ensure file existence with baseline entry for empty environments
        append_line(log_file, json.dumps({'timestamp': ts, 'type': 'init', 'verified': False, 'reason': 'no_anchor_chain'}))

    audit_marker(f'<!-- COLD_STORAGE_VERIFY: UPDATED {ts} -->', ROOT)
    print(f'VERIFICATION_COMPLETED entries_written={sum(1 for _ in log_file.open("r", encoding="utf-8"))}')


def main() -> int:
    verify()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
