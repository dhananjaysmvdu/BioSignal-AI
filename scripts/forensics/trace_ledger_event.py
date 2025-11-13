#!/usr/bin/env python3
"""
Phase XVII - Instruction 93: Forensic Traceback Tool

Search snapshots for the first appearance of an event/tag and display the matching ledger entry.
Optionally verify snapshot hash and write latest result for portal consumption.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path
from typing import Optional

# Add forensics directory to path for forensics_utils import
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forensics_utils import utc_now_iso, compute_sha256

SNAPSHOTS = ROOT / 'snapshots'
MIRRORS = ROOT / 'mirrors'
FORENSICS = ROOT / 'forensics'


def load_snapshot_hashes() -> list[dict]:
    p = SNAPSHOTS / 'ledger_snapshot_hash.json'
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def iter_snapshots():
    for p in sorted(SNAPSHOTS.glob('ledger_snapshot_*.tar.gz')):
        yield p


def search_snapshot_for_event(bundle: Path, needle: str) -> Optional[dict]:
    try:
        with tarfile.open(bundle, 'r:gz') as tar:
            # Try to locate ledger file within archive
            member = next((m for m in tar.getmembers() if m.name.endswith('governance_provenance_ledger.jsonl')), None)
            if not member:
                return None
            f = tar.extractfile(member)
            if not f:
                return None
            for raw in f:
                try:
                    line = raw.decode('utf-8', errors='ignore')
                except Exception:
                    continue
                if needle in line:
                    try:
                        return json.loads(line)
                    except Exception:
                        return {'raw': line}
    except Exception:
        return None
    return None


def load_anchor_chain_tail() -> Optional[dict]:
    chain = MIRRORS / 'anchor_chain.json'
    if not chain.exists():
        return None
    try:
        data = json.loads(chain.read_text(encoding='utf-8'))
        return data[-1] if data else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('query', help='Event ID or tag to search for')
    ap.add_argument('--verify-hash', action='store_true', help='Recompute snapshot hash and confirm match')
    ap.add_argument('--write-latest', action='store_true', help='Write latest trace output to forensics/last_trace.json for portal use')
    args = ap.parse_args()

    result = {
        'query': args.query,
        'timestamp': utc_now_iso(),
        'match': None,
        'snapshot': None,
        'snapshot_hash_match': None,
        'anchor_chain_tail': load_anchor_chain_tail(),
    }

    hashes = load_snapshot_hashes()
    for bundle in iter_snapshots():
        entry = search_snapshot_for_event(bundle, args.query)
        if entry is not None:
            result['match'] = entry
            result['snapshot'] = bundle.name
            if args.verify-hash:
                rec = next((r for r in hashes if r.get('file') == bundle.name), None)
                if rec:
                    result['snapshot_hash_match'] = (rec.get('sha256') == compute_sha256(bundle))
            break

    print(json.dumps(result, indent=2))
    if args.write_latest:
        FORENSICS.mkdir(parents=True, exist_ok=True)
        (FORENSICS / 'last_trace.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
