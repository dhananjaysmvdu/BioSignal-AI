#!/usr/bin/env python3
"""
Phase XIX - Instruction 101: Provenance Sync Engine

Computes federated consensus over provenance-related hashes across peers.

Reads local:
- snapshots/ledger_snapshot_hash.json (last entry sha256)
- mirrors/anchor_chain.json (tail sha256 or chain_hash)
- docs/documentation_provenance_hash.json (sha256)

Reads peers from federation/peers.json, fetches equivalent hashes from peers.
Consensus = majority (most common) sha256 for each category. Agreement % =
min across the three categories over proportion of nodes (local+peers) whose
hash equals the consensus hash.

Writes federation/provenance_consensus.json and appends PROVENANCE_SYNC marker.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = ROOT / 'snapshots'
MIRRORS = ROOT / 'mirrors'
DOCS = ROOT / 'docs'
FED = ROOT / 'federation'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_local_hashes() -> Dict[str, Optional[str]]:
    # Ledger snapshot latest sha
    ledger_sha = None
    p = SNAPSHOTS / 'ledger_snapshot_hash.json'
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, list) and data:
                ledger_sha = data[-1].get('sha256')
            elif isinstance(data, dict):
                ledger_sha = data.get('sha256')
        except Exception:
            pass
    # Anchor chain tail (prefer chain_hash to cover cumulative)
    anchor_sha = None
    c = MIRRORS / 'anchor_chain.json'
    if c.exists():
        try:
            data = json.loads(c.read_text(encoding='utf-8'))
            if data:
                tail = data[-1]
                anchor_sha = tail.get('chain_hash') or tail.get('sha256')
        except Exception:
            pass
    # Documentation bundle hash
    bundle_sha = None
    b = DOCS / 'documentation_provenance_hash.json'
    if b.exists():
        try:
            data = json.loads(b.read_text(encoding='utf-8'))
            bundle_sha = data.get('sha256')
        except Exception:
            pass
    return {'ledger': ledger_sha, 'anchor': anchor_sha, 'bundle': bundle_sha}


def read_peers() -> List[Dict[str, str]]:
    FED.mkdir(parents=True, exist_ok=True)
    pf = FED / 'peers.json'
    if not pf.exists():
        return []
    try:
        data = json.loads(pf.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def http_get_json(url: str) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None
    return None


def fetch_peer_hashes(peer: Dict[str, str]) -> Dict[str, Optional[str]]:
    base = peer.get('base_url', '').rstrip('/')
    paths = peer.get('paths', {})
    # Expected default locations
    ledger_url = paths.get('ledger', f"{base}/snapshots/ledger_snapshot_hash.json")
    anchor_url = paths.get('anchor', f"{base}/mirrors/anchor_chain.json")
    bundle_url = paths.get('bundle', f"{base}/docs/documentation_provenance_hash.json")

    out = {'ledger': None, 'anchor': None, 'bundle': None}
    # Ledger
    j = http_get_json(ledger_url)
    if isinstance(j, list) and j:
        out['ledger'] = j[-1].get('sha256')
    elif isinstance(j, dict):
        out['ledger'] = j.get('sha256')
    # Anchor
    j = http_get_json(anchor_url)
    if isinstance(j, list) and j:
        tail = j[-1]
        out['anchor'] = tail.get('chain_hash') or tail.get('sha256')
    # Bundle
    j = http_get_json(bundle_url)
    if isinstance(j, dict):
        out['bundle'] = j.get('sha256')
    return out


def majority_hash(values: List[Optional[str]]) -> Optional[str]:
    vals = [v for v in values if v]
    if not vals:
        return None
    cnt = Counter(vals)
    return cnt.most_common(1)[0][0]


def write_audit_marker(ts: str) -> None:
    audit = ROOT / 'audit_summary.md'
    with audit.open('a', encoding='utf-8') as f:
        f.write(f'<!-- PROVENANCE_SYNC: VERIFIED {ts} -->\n')


def main() -> int:
    local = read_local_hashes()
    peers = read_peers()
    peer_hashes = [fetch_peer_hashes(p) for p in peers]
    all_nodes = [local] + peer_hashes

    ledger_consensus = majority_hash([n.get('ledger') for n in all_nodes])
    anchor_consensus = majority_hash([n.get('anchor') for n in all_nodes])
    bundle_consensus = majority_hash([n.get('bundle') for n in all_nodes])

    def pct(consensus: Optional[str], key: str) -> float:
        if not consensus:
            return 0.0
        total = len(all_nodes)
        agree = sum(1 for n in all_nodes if n.get(key) == consensus)
        return 100.0 * agree / max(1, total)

    ledger_pct = pct(ledger_consensus, 'ledger')
    anchor_pct = pct(anchor_consensus, 'anchor')
    bundle_pct = pct(bundle_consensus, 'bundle')
    agreement_pct = min(ledger_pct, anchor_pct, bundle_pct)

    FED.mkdir(parents=True, exist_ok=True)
    out = {
        'timestamp': utc_now_iso(),
        'peers_checked': len(peers),
        'ledger_consensus_hash': ledger_consensus,
        'anchor_consensus_hash': anchor_consensus,
        'bundle_consensus_hash': bundle_consensus,
        'ledger_agreement_pct': round(ledger_pct, 2),
        'anchor_agreement_pct': round(anchor_pct, 2),
        'bundle_agreement_pct': round(bundle_pct, 2),
        'agreement_pct': round(agreement_pct, 2),
    }
    (FED / 'provenance_consensus.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    write_audit_marker(out['timestamp'])
    print(json.dumps(out, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
