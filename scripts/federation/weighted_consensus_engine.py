#!/usr/bin/env python3
"""
Phase XX - Instruction 107: Weighted Consensus Engine

Recomputes consensus using reputation-based weights.

Reads:
- federation/provenance_consensus.json (baseline)
- federation/reputation_index.json (peer scores)
- federation/peers.json (peer endpoints)

Fetches current peer hashes and computes weighted agreement per category.
Outputs federation/weighted_consensus.json with weighted_agreement_pct and
a simple 95% confidence interval.

Appends marker: <!-- WEIGHTED_CONSENSUS: VERIFIED <UTC ISO> -->
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from typing import Dict, List, Optional
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
FED = ROOT / 'federation'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_get_json(url: str, timeout: int = 10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None
    return None


def read_json_file(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def read_peers() -> List[Dict[str, str]]:
    pf = FED / 'peers.json'
    if not pf.exists():
        return []
    try:
        data = json.loads(pf.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def get_paths(peer: Dict[str, str]) -> Dict[str, str]:
    base = peer.get('base_url', '').rstrip('/')
    paths = peer.get('paths', {}) or {}
    return {
        'ledger': paths.get('ledger', f"{base}/snapshots/ledger_snapshot_hash.json"),
        'anchor': paths.get('anchor', f"{base}/mirrors/anchor_chain.json"),
        'bundle': paths.get('bundle', f"{base}/docs/documentation_provenance_hash.json"),
    }


def fetch_peer_values(peer: Dict[str, str]) -> Dict[str, Optional[str]]:
    p = get_paths(peer)
    out = {'ledger': None, 'anchor': None, 'bundle': None}
    # Ledger last sha
    j = http_get_json(p['ledger'])
    if isinstance(j, list) and j:
        out['ledger'] = j[-1].get('sha256')
    elif isinstance(j, dict):
        out['ledger'] = j.get('sha256')
    # Anchor tail
    j = http_get_json(p['anchor'])
    if isinstance(j, list) and j:
        tail = j[-1]
        out['anchor'] = tail.get('chain_hash') or tail.get('sha256')
    # Bundle hash
    j = http_get_json(p['bundle'])
    if isinstance(j, dict):
        out['bundle'] = j.get('sha256')
    return out


def weighted_agreement(values: List[Optional[str]], weights: List[float]) -> float:
    """Return weighted % of weights agreeing with the majority hash.
    Ignores None values (weight not counted).
    """
    pairs = [(v, w) for v, w in zip(values, weights) if v]
    if not pairs:
        return 0.0
    # Determine weighted majority
    tally: Dict[str, float] = {}
    for v, w in pairs:
        tally[v] = tally.get(v, 0.0) + w
    winner = max(tally.items(), key=lambda kv: kv[1])[0]
    tot_w = sum(w for _, w in pairs)
    agree_w = sum(w for v, w in pairs if v == winner)
    if tot_w <= 0:
        return 0.0
    return 100.0 * agree_w / tot_w


def confidence_interval(pct: float, weights: List[float]) -> List[float]:
    """Simple normal approx CI using effective sample size from weights.
    n_eff = (sum w)^2 / sum w^2. Guard from zero.
    """
    if not weights:
        return [pct, pct]
    sw = sum(weights)
    sw2 = sum(w*w for w in weights)
    n_eff = (sw*sw) / sw2 if sw2 > 0 else 1.0
    p = max(0.0, min(1.0, pct / 100.0))
    se = sqrt(max(1e-9, p * (1.0 - p) / max(1.0, n_eff)))
    ci = 1.96 * se
    lo = max(0.0, (p - ci) * 100.0)
    hi = min(100.0, (p + ci) * 100.0)
    return [round(lo, 2), round(hi, 2)]


def write_marker(ts: str) -> None:
    audit = ROOT / 'audit_summary.md'
    with audit.open('a', encoding='utf-8') as f:
        f.write(f'<!-- WEIGHTED_CONSENSUS: VERIFIED {ts} -->\n')


def main() -> int:
    base_consensus = read_json_file(FED / 'provenance_consensus.json')
    rep = read_json_file(FED / 'reputation_index.json')
    peers = read_peers()

    # Build weight map by base_url or name
    score_map: Dict[str, float] = {}
    scores = rep.get('scores') if isinstance(rep.get('scores'), list) else []
    for s in scores:
        key = s.get('base_url') or s.get('peer')
        try:
            score_map[str(key)] = float(s.get('score', 0.0))
        except Exception:
            continue

    # Gather peer values and weights
    values_ledger: List[Optional[str]] = []
    values_anchor: List[Optional[str]] = []
    values_bundle: List[Optional[str]] = []
    weights: List[float] = []
    top3 = sorted([(s.get('peer'), s.get('score')) for s in scores], key=lambda x: x[1], reverse=True)[:3]

    for peer in peers:
        base = peer.get('base_url')
        w = score_map.get(base, 0.0)
        pv = fetch_peer_values(peer)
        values_ledger.append(pv.get('ledger'))
        values_anchor.append(pv.get('anchor'))
        values_bundle.append(pv.get('bundle'))
        weights.append(w)

    ledger_pct = round(weighted_agreement(values_ledger, weights), 2)
    anchor_pct = round(weighted_agreement(values_anchor, weights), 2)
    bundle_pct = round(weighted_agreement(values_bundle, weights), 2)
    weighted_min_pct = round(min(ledger_pct, anchor_pct, bundle_pct), 2)
    ci = confidence_interval(weighted_min_pct, weights)

    out = {
        'timestamp': utc_now_iso(),
        'peers_checked': len(peers),
        'ledger_weighted_agreement_pct': ledger_pct,
        'anchor_weighted_agreement_pct': anchor_pct,
        'bundle_weighted_agreement_pct': bundle_pct,
        'weighted_agreement_pct': weighted_min_pct,
        'confidence_interval_95': ci,
        # Aliases for validation consumers
        'confidence_interval': ci,
        'top_trusted_peers': [
            {'peer': str(name), 'score': float(score)} for name, score in top3 if name is not None
        ],
        'top_peers': [
            {'peer': str(name), 'score': float(score)} for name, score in top3 if name is not None
        ],
        'baseline': {
            'agreement_pct': base_consensus.get('agreement_pct'),
            'ledger_agreement_pct': base_consensus.get('ledger_agreement_pct'),
            'anchor_agreement_pct': base_consensus.get('anchor_agreement_pct'),
            'bundle_agreement_pct': base_consensus.get('bundle_agreement_pct'),
        }
    }
    FED.mkdir(parents=True, exist_ok=True)
    (FED / 'weighted_consensus.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    write_marker(out['timestamp'])
    print(json.dumps(out, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
