"""Adaptive Certification Intelligence (Phase XI Instruction 59).

Learns simple relationships from telemetry and adjusts alert thresholds.
Persists policy to config/certification_policy.json and appends audit marker.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT/"results"/"integration_resilience_report.json"
FED_STATUS = ROOT/"federation"/"federation_status.json"
HEAL_STATUS = ROOT/"self_healing"/"self_healing_status.json"
POLICY = ROOT/"config"/"certification_policy.json"
AUDIT = ROOT/"audit_summary.md"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    report = load_json(INTEGRATION)
    fed = load_json(FED_STATUS)
    heal = load_json(HEAL_STATUS)

    fii = float(fed.get("federation_integrity_index", 98.0))
    # estimate recovery success from heal events
    events = heal.get("events", [])
    rec_rate = 100.0
    if isinstance(events, list) and events:
        successes = sum(1 for e in events if "restored" in json.dumps(e).lower())
        rec_rate = (successes/len(events))*100.0

    # Base thresholds (defaults)
    drift_tolerance_pct = 1.0
    guardrail_window_min = 2

    if fii >= 99.0:
        drift_tolerance_pct = 0.8
    if rec_rate < 98.0:
        guardrail_window_min = 5

    policy = {
        "timestamp": utc_iso(),
        "drift_tolerance_pct": drift_tolerance_pct,
        "guardrail_window_min": guardrail_window_min,
        "inputs": {
            "fii": fii,
            "recovery_rate": rec_rate,
        }
    }
    POLICY.parent.mkdir(parents=True, exist_ok=True)
    POLICY.write_text(json.dumps(policy, indent=2), encoding="utf-8")

    # Append audit marker
    if AUDIT.exists():
        with AUDIT.open("a", encoding="utf-8") as fh:
            fh.write(f"<!-- ADAPTIVE_CERTIFICATION: UPDATED {utc_iso()} -->\n")

    print(json.dumps(policy))


if __name__ == "__main__":
    main()
