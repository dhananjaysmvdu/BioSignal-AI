"""Meta-Governance Learning Engine (Phase XII Instruction 65)."""
from __future__ import annotations

import json
from statistics import mean
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCHANGE = ROOT/"results"/"federation_peer_exchange_report.json"
ETHICS = ROOT/"results"/"ethics_audit_bridge_report.json"
FORECAST = ROOT/"forecast"/"schema_drift_forecast.json"
OUT = ROOT/"governance"/"meta_policy_recommendations.json"
AUDIT = ROOT/"audit_summary.md"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def main():
    exchange = load(EXCHANGE)
    ethics = load(ETHICS)
    forecast = load(FORECAST)
    peers = exchange.get('peers', []) if isinstance(exchange, dict) else []
    drift_vals = [float(p.get('peer_drift_tolerance_pct', 1.0)) for p in peers if isinstance(p, dict)]
    guard_vals = [float(p.get('peer_guardrail_window_min', 2)) for p in peers if isinstance(p, dict)]
    rec = {
        'timestamp': utc_iso(),
        'recommended_drift_tolerance_pct': round(mean(drift_vals), 3) if drift_vals else None,
        'recommended_guardrail_window_min': round(mean(guard_vals), 3) if guard_vals else None,
        'context': {
            'schema_drift_prob': forecast.get('drift_prob'),
            'recent_ethics_bias': ethics.get('bias'),
            'peers_considered': len(peers)
        }
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rec, indent=2), encoding='utf-8')
    if AUDIT.exists():
        with AUDIT.open('a', encoding='utf-8') as fh:
            fh.write(f"<!-- META_GOVERNANCE_LEARNING: UPDATED {utc_iso()} -->\n")
    print(json.dumps(rec))


if __name__ == '__main__':
    main()
