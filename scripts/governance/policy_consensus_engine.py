"""Distributed Policy Consensus Engine (Phase XII Instruction 68)."""
from __future__ import annotations

import json
from statistics import median
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCHANGE = ROOT/"results"/"federation_peer_exchange_report.json"
POLICY = ROOT/"config"/"certification_policy.json"
LOG = ROOT/"governance"/"policy_consensus_log.jsonl"
AUDIT = ROOT/"audit_summary.md"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def append_log(entry: dict):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(entry) + '\n')


def main():
    exchange = load(EXCHANGE)
    peers = exchange.get('peers', []) if isinstance(exchange, dict) else []
    drift_vals = [float(p.get('peer_drift_tolerance_pct')) for p in peers if 'peer_drift_tolerance_pct' in p]
    guard_vals = [float(p.get('peer_guardrail_window_min')) for p in peers if 'peer_guardrail_window_min' in p]
    consensus_ratio = 0.0
    if peers:
        consensus_ratio = min(1.0, max(len(drift_vals), len(guard_vals)) / max(1, len(peers)))
    decision = {
        'timestamp': utc_iso(),
        'consensus_ratio': round(consensus_ratio, 3),
        'action': 'none'
    }
    if consensus_ratio >= 0.75 and (drift_vals or guard_vals):
        # Compute medians
        new_policy = load(POLICY)
        if drift_vals:
            new_policy['drift_tolerance_pct'] = float(median(drift_vals))
        if guard_vals:
            new_policy['guardrail_window_min'] = float(median(guard_vals))
        POLICY.parent.mkdir(parents=True, exist_ok=True)
        POLICY.write_text(json.dumps(new_policy, indent=2), encoding='utf-8')
        decision['action'] = 'policy_updated'
        if AUDIT.exists():
            with AUDIT.open('a', encoding='utf-8') as fh:
                fh.write(f"<!-- POLICY_CONSENSUS: REACHED {utc_iso()} -->\n")
    append_log(decision)
    print(json.dumps(decision))


if __name__ == '__main__':
    main()
