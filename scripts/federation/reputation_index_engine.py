#!/usr/bin/env python3
"""
Phase XX - Instruction 106: Reputation Index Engine

Computes dynamic peer reputation based on:
- agreement_score = mean of last up-to-5 agreement_pct values (current consensus + last drift log entries)
- stability_penalty = (# of drifts > 10%) * 0.02
- ethics_bonus = +0.05 if peer fairness >= 98% (from ethics endpoint when available)

Final score = clamp(agreement_score - stability_penalty + ethics_bonus, 0, 100)

Writes federation/reputation_index.json and appends REPUTATION_INDEX marker.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
FED = ROOT / 'federation'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_get_text(url: str, timeout: int = 10) -> Optional[str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read().decode('utf-8')
    except Exception:
        return None
    return None


def http_get_json(url: str, timeout: int = 10) -> Optional[dict | list]:
    txt = http_get_text(url, timeout=timeout)
    if txt is None:
        return None
    try:
        return json.loads(txt)
    except Exception:
        return None


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


def get_paths(peer: Dict[str, str]) -> Dict[str, str]:
    base = peer.get('base_url', '').rstrip('/')
    paths = peer.get('paths', {}) or {}
    return {
        'consensus': paths.get('consensus', f"{base}/federation/provenance_consensus.json"),
        'trust': paths.get('trust', f"{base}/federation/trust_consensus_report.json"),
        'drift': paths.get('drift', f"{base}/federation/provenance_drift_log.jsonl"),
        'ethics': paths.get('ethics', f"{base}/results/fairness_summary.json"),
    }


def last_agreements(consensus_url: str, drift_url: str, k: int = 5) -> List[float]:
    vals: List[float] = []
    c = http_get_json(consensus_url)
    if isinstance(c, dict):
        try:
            ap = float(c.get('agreement_pct', 0))
            vals.append(ap)
        except Exception:
            pass
    # Fill remaining from drift log (most recent lines)
    txt = http_get_text(drift_url)
    if txt:
        lines = [ln for ln in txt.strip().splitlines() if ln.strip()]
        for ln in lines[-(k-1):]:
            try:
                j = json.loads(ln)
                ap = float(j.get('agreement_pct', 0))
                vals.append(ap)
            except Exception:
                continue
    return vals[:k]


def count_large_drifts(drift_url: str, threshold: float = 10.0) -> int:
    txt = http_get_text(drift_url)
    if not txt:
        return 0
    cnt = 0
    for ln in txt.strip().splitlines():
        try:
            j = json.loads(ln)
            ap = float(j.get('agreement_pct', 0))
            if ap < (100.0 - threshold):
                cnt += 1
        except Exception:
            continue
    return cnt


def ethics_bonus(ethics_url: str) -> float:
    j = http_get_json(ethics_url)
    if isinstance(j, dict):
        for key in ('fairness_min_pct', 'overall_min_pct', 'min_fairness_pct', 'min_pct'):
            try:
                v = float(j.get(key))
                if v >= 98.0:
                    return 0.05
            except Exception:
                continue
        # Some peers expose nested {metrics:{fairness_min_pct:..}}
        metrics = j.get('metrics') if isinstance(j.get('metrics'), dict) else None
        if metrics:
            try:
                v = float(metrics.get('fairness_min_pct', 0))
                if v >= 98.0:
                    return 0.05
            except Exception:
                pass
    return 0.0


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def write_audit_marker(ts: str) -> None:
    audit = ROOT / 'audit_summary.md'
    with audit.open('a', encoding='utf-8') as f:
        f.write(f'<!-- REPUTATION_INDEX: UPDATED {ts} -->\n')


def main() -> int:
    peers = read_peers()
    results: List[Dict[str, object]] = []

    for peer in peers:
        name = peer.get('name') or peer.get('base_url', 'unknown')
        p = get_paths(peer)
        agreements = last_agreements(p['consensus'], p['drift'], k=5)
        if agreements:
            agreement_score = sum(agreements) / len(agreements)
        else:
            agreement_score = 0.0
        drifts = count_large_drifts(p['drift'], threshold=10.0)
        stability_penalty = drifts * 0.02
        bonus = ethics_bonus(p['ethics'])
        final = clamp(agreement_score - stability_penalty + bonus, 0.0, 100.0)
        results.append({
            'peer': name,
            'base_url': peer.get('base_url'),
            'agreement_score': round(agreement_score, 2),
            'stability_penalty': round(stability_penalty, 4),
            'ethics_bonus': round(bonus, 4),
            'score': round(final, 2),
            'drifts_over_10pct': drifts,
            'samples_used': len(agreements),
        })

    out = {
        'timestamp': utc_now_iso(),
        'peers_scored': len(results),
        'scores': sorted(results, key=lambda x: x['score'], reverse=True),
    }

    FED.mkdir(parents=True, exist_ok=True)
    (FED / 'reputation_index.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    write_audit_marker(out['timestamp'])
    print(json.dumps(out, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
