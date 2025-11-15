#!/usr/bin/env python3
"""
Phase XVII - Instruction 91: Immutable Ledger Snapshotter

Reads governance ledger artifacts and creates a timestamped tar.gz snapshot with a SHA-256 record.
Retains only the last 10 snapshots.
Appends audit marker to audit_summary.md.
"""
from __future__ import annotations

import json
import sys
import tarfile
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


def find_ledger_files(artifact_dir: Path) -> list[Path]:
    candidates = [
        artifact_dir / 'governance_provenance_ledger.jsonl',
        artifact_dir / 'governance_ledger_hash.json',
    ]
    return [p for p in candidates if p.exists()]


def write_hash_record(root_path: Path, snapshots_dir: Path, bundle: Path, ts: str) -> None:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    rec_path = snapshots_dir / 'ledger_snapshot_hash.json'
    rec = []
    if rec_path.exists():
        try:
            rec = json.loads(rec_path.read_text(encoding='utf-8'))
            if isinstance(rec, dict):
                rec = [rec]
            if not isinstance(rec, list):
                rec = []
        except Exception as e:
            log_forensics_event({'error': 'read_snapshot_hash_failed', 'exc': str(e)})
            rec = []
    try:
        sha = compute_sha256(bundle)
        if sha:
            rec.append({'timestamp': ts, 'file': bundle.name, 'sha256': sha})
        rec_path.write_text(json.dumps(rec, indent=2), encoding='utf-8')
    except Exception as e:
        log_forensics_event({'error': 'write_snapshot_hash_failed', 'exc': str(e)})


def prune_old_snapshots(root_path: Path, snapshots_dir: Path, limit: int = 10) -> None:
    bundles = sorted(snapshots_dir.glob('ledger_snapshot_*.tar.gz'))
    to_delete = bundles[:-limit]
    for p in to_delete:
        try:
            p.unlink()
        except Exception as e:
            log_forensics_event({'error': 'prune_snapshot_failed', 'file': str(p), 'exc': str(e)})


def main() -> int:
    artifact_dir = ROOT / 'artifacts'
    snapshots_dir = ROOT / 'snapshots'
    files = find_ledger_files(artifact_dir)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_now_iso().replace(':', '').replace('-', '')
    bundle = snapshots_dir / f'ledger_snapshot_{ts}.tar.gz'
    try:
        with tarfile.open(bundle, 'w:gz') as tar:
            for fp in files:
                arcname = fp.relative_to(ROOT).as_posix()
                tar.add(fp, arcname=arcname)
    except Exception as e:
        log_forensics_event({'error': 'snapshot_tar_failed', 'exc': str(e)})
        return 2
    write_hash_record(ROOT, snapshots_dir, bundle, ts)
    audit_marker(f'<!-- LEDGER_SNAPSHOT: SAVED {ts} -->', ROOT)
    prune_old_snapshots(ROOT, snapshots_dir)
    print(f'SNAPSHOT_BUNDLE_CREATED {bundle.name} files={len(files)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
