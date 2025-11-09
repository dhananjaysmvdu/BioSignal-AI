#!/usr/bin/env python3
"""
Compliance Justification Engine
- Reads configs/governance_policy.json and reports/provenance_forecast.json
- Generates natural-language explanation for current policy settings
- Writes full rationale to reports/compliance_rationale.md
- Appends summarized rationale to reports/audit_summary.md under marker <!-- POLICY_EXPLAIN:BEGIN -->
- Appends trace entry to logs/decision_trace.json
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_POLICY = os.path.join(ROOT, "configs", "governance_policy.json")
FORECAST_JSON = os.path.join(ROOT, "reports", "provenance_forecast.json")
SUMMARY_MD = os.path.join(ROOT, "reports", "audit_summary.md")
RATIONALE_MD = os.path.join(ROOT, "reports", "compliance_rationale.md")
TRACE_JSON = os.path.join(ROOT, "logs", "decision_trace.json")
POLICY_EXPLAIN_MARKER = "<!-- POLICY_EXPLAIN:BEGIN -->"


def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def classify_decision(policy: Dict[str, Any], forecast: Dict[str, Any]) -> str:
    drift_prob = float(forecast.get("predicted_drift_probability_pct", 0.0) or 0.0) / 100.0
    depth = policy.get("audit_depth")
    if depth == "full" and drift_prob > 0.5:
        return "increase_audit_depth"
    if depth == "moderate" and 0.2 < drift_prob <= 0.5:
        return "maintain_elevated_state"
    if depth == "light" and drift_prob <= 0.2:
        return "maintain_low_state"
    return "state_transition"


def build_rationale(policy: Dict[str, Any], forecast: Dict[str, Any]) -> str:
    drift_prob = float(forecast.get("predicted_drift_probability_pct", 0.0) or 0.0) / 100.0
    conf = float(forecast.get("confidence_pct", 0.0) or 0.0) / 100.0
    depth = policy.get("audit_depth", "unknown")
    drift_threshold = policy.get("drift_threshold")

    # Determine reason phrases
    if depth == "full":
        reason = (
            f"The audit depth was increased to \"full\" because the predicted drift probability "
            f"({drift_prob:.2f}) exceeded the 0.5 threshold, indicating elevated systemic variance risk."
        )
    elif depth == "moderate":
        reason = (
            f"Audit depth set to \"moderate\" since predicted drift probability ({drift_prob:.2f}) resides in the medium-risk band (0.2–0.5)."
        )
    elif depth == "light":
        reason = (
            f"Audit depth remains \"light\" as predicted drift probability ({drift_prob:.2f}) is at or below 0.2, suggesting stable provenance."
        )
    else:
        reason = (
            f"Audit depth set to \"{depth}\" based on current drift probability ({drift_prob:.2f})."
        )

    sensitivity = (
        f"The drift threshold was {'lowered' if depth=='full' else 'set'} to {drift_threshold} to "
        f"{'tighten anomaly sensitivity' if depth=='full' else 'balance sensitivity with operational cost'}."
    )

    confidence_clause = (
        f"Confidence remains {'high' if conf >= 0.75 else 'moderate'} ({conf:.2f}), supporting this calibration of audit rigor."
    )

    remediation_clause = ""
    if depth == "full":
        remediation_clause = "Remediation trigger posture is elevated to ensure rapid containment if drift manifests."
    elif depth == "moderate":
        remediation_clause = "Remediation posture remains on-demand, avoiding unnecessary churn."
    else:
        remediation_clause = "Remediation posture stays in standby to minimize overhead."

    rationale = (
        "Compliance Rationale:\n" + reason + " " + sensitivity + " " + confidence_clause + " " + remediation_clause + "\n"
    )
    return rationale


def append_summary_marker(rationale: str):
    lines = []
    if os.path.exists(SUMMARY_MD):
        with open(SUMMARY_MD, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    # remove prior POLICY_EXPLAIN section if present
    if POLICY_EXPLAIN_MARKER in "\n".join(lines):
        idx = [i for i, ln in enumerate(lines) if POLICY_EXPLAIN_MARKER in ln]
        if idx:
            lines = lines[: idx[0]]
    summary_line = rationale.splitlines()[0] if rationale else "Policy rationale generated."
    block = ["", POLICY_EXPLAIN_MARKER, "## Policy Rationale Summary", summary_line]
    lines.extend(block)
    with open(SUMMARY_MD, "w", encoding="utf-8") as fw:
        fw.write("\n".join(lines) + "\n")


def append_decision_trace(decision: str, policy: Dict[str, Any], forecast: Dict[str, Any], rationale: str):
    os.makedirs(os.path.dirname(TRACE_JSON), exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "inputs": {
            "drift_probability": round(float(forecast.get("predicted_drift_probability_pct", 0))/100.0, 4),
            "confidence": round(float(forecast.get("confidence_pct", 0))/100.0, 4),
        },
        "rationale": rationale.splitlines()[0][:240],  # first line truncated to 240 chars
    }
    trace = []
    if os.path.exists(TRACE_JSON):
        try:
            with open(TRACE_JSON, "r", encoding="utf-8") as f:
                trace = json.load(f)
                if not isinstance(trace, list):
                    trace = []
        except Exception:
            trace = []
    trace.append(entry)
    with open(TRACE_JSON, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2)


def main() -> int:
    policy = load_json(CONFIG_POLICY)
    forecast = load_json(FORECAST_JSON)
    decision = classify_decision(policy, forecast)
    rationale = build_rationale(policy, forecast)

    os.makedirs(os.path.dirname(RATIONALE_MD), exist_ok=True)
    with open(RATIONALE_MD, "w", encoding="utf-8") as fw:
        fw.write(rationale)

    append_summary_marker(rationale)
    append_decision_trace(decision, policy, forecast, rationale)

    print(rationale)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
