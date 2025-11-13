#!/usr/bin/env python3
"""
Governance Decision Traceability Logger

Records autonomous governance actions with full context:
- Timestamp, action type, parameter changes
- Trigger conditions, reasoning, audit reference
- Writes to exports/decision_trace_log.jsonl (append-only)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "exports" / "decision_trace_log.jsonl"


def log_decision(
    action: str,
    parameter_change: dict,
    trigger: str,
    reason: str,
    audit_reference: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Append a governance decision entry to the trace log.
    
    Args:
        action: Type of action (e.g., "adaptive_lr_update", "forecast_recalibration")
        parameter_change: Dict of parameter name -> (old_value, new_value)
        trigger: What triggered this decision (e.g., "FDI threshold breach")
        reason: Human-readable justification
        audit_reference: Reference to related audit marker or report
        metadata: Additional context
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    entry = {
        "id": generate_trace_id(),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "action": action,
        "parameter_change": parameter_change,
        "trigger": trigger,
        "reason": reason,
        "audit_reference": audit_reference,
        "metadata": metadata or {},
    }
    
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"✅ Decision trace logged: {action} (ID: {entry['id']})")


def generate_trace_id() -> str:
    """Generate unique trace ID based on timestamp."""
    return f"DT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def read_latest_decisions(n: int = 5) -> list[dict]:
    """Read last N decisions from trace log."""
    if not LOG_PATH.exists():
        return []
    
    decisions = []
    try:
        with LOG_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    decisions.append(json.loads(line))
    except Exception as e:
        print(f"⚠️ Error reading decision trace log: {e}", file=sys.stderr)
        return []
    
    return decisions[-n:]


def main() -> None:
    """Demo: Log a sample governance decision."""
    log_decision(
        action="adaptive_lr_update",
        parameter_change={"learning_rate_factor": ("1.0", "1.2")},
        trigger="FDI=0.0% (excellent) + CS=2.1 (stable)",
        reason="Forecast accuracy excellent; increasing adaptation rate to accelerate convergence",
        audit_reference="ADAPTIVE_V2: 2025-11-13T16:35:00+00:00",
        metadata={"controller_version": "v2.0", "integrity_predicted": 98.0},
    )
    
    # Example: Log calibration decision
    log_decision(
        action="forecast_recalibration",
        parameter_change={"calibration_error": ("0.0", "0.5"), "forecast_bias": ("0.0", "+0.5")},
        trigger="Q1 2026 predictive window complete",
        reason="Calibration cycle completed; actual integrity 97.5% vs predicted 98.0%",
        audit_reference="PREDICTIVE_CALIBRATION: 2025-11-13T17:15:00+00:00",
        metadata={"samples_compared": 1, "period": "2026-Q1"},
    )
    
    print(f"\n📋 Latest 5 decisions:")
    for dec in read_latest_decisions(5):
        print(f"   {dec['id']}: {dec['action']} — {dec['reason'][:60]}...")


if __name__ == "__main__":
    main()
