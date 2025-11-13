#!/usr/bin/env python3
"""
Phase XVII - Instruction 91: Immutable Ledger Snapshotter

Reads governance ledger artifacts and creates a timestamped tar.gz snapshot with a SHA-256 record.
Retains only the last 10 snapshots.
Appends audit marker to audit_summary.md.
"""
from __future__ import annotations

import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / 'artifacts'
SNAPSHOTS = ROOT / 'snapshots'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def find_ledger_files() -> list[Path]:
    candidates = [
        ARTIFACTS / 'governance_provenance_ledger.jsonl',
        ARTIFACTS / 'governance_ledger_hash.json',
        ROOT / 'artifacts' / 'governance_provenance_ledger.jsonl',
        ROOT / 'artifacts' / 'governance_ledger_hash.json',
    ]
    files = [p for p in candidates if p.exists()]
    return files


def write_hash_record(bundle: Path, ts: str) -> None:
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    rec_path = SNAPSHOTS / 'ledger_snapshot_hash.json'
    rec = []
    if rec_path.exists():
        try:
            rec = json.loads(rec_path.read_text(encoding='utf-8'))
            if isinstance(rec, dict):
                # migrate to list format
                rec = [rec]
        except Exception:
            rec = []
    rec.append({'timestamp': ts, 'file': bundle.name, 'sha256': sha256_path(bundle)})
    rec_path.write_text(json.dumps(rec, indent=2), encoding='utf-8')


def append_audit_marker(ts: str) -> None:
    audit = ROOT / 'audit_summary.md'
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open('a', encoding='utf-8') as f:
        f.write(f'<!-- LEDGER_SNAPSHOT: SAVED {ts} -->\n')


def prune_old_snapshots() -> None:
    bundles = sorted(SNAPSHOTS.glob('ledger_snapshot_*.tar.gz'))
    # retain last 10
    to_delete = bundles[:-10]
    for p in to_delete:
        try:
            p.unlink()
        except Exception:
            pass


def main() -> int:
    files = find_ledger_files()
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    ts = utc_now_iso().replace(':', '').replace('-', '')
    bundle = SNAPSHOTS / f'ledger_snapshot_{ts}.tar.gz'

    with tarfile.open(bundle, 'w:gz') as tar:
        for fp in files:
            arcname = fp.relative_to(ROOT).as_posix()
            tar.add(fp, arcname=arcname)

    write_hash_record(bundle, ts)
    append_audit_marker(ts)
    prune_old_snapshots()
    print(f'Created {bundle}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
