#!/usr/bin/env python3
"""
Prescriptive Governance Controller
- Reads reports/provenance_forecast.json
- Applies decision rules to set audit intensity and thresholds
- Writes configs/governance_policy.json
- Appends a policy decision summary to reports/audit_summary.md after marker <!-- POLICY_ADJUST:BEGIN -->
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORTS_DIR = os.path.join(ROOT, "reports")
FORECAST_JSON = os.path.join(REPORTS_DIR, "provenance_forecast.json")
SUMMARY_MD = os.path.join(REPORTS_DIR, "audit_summary.md")
CONFIGS_DIR = os.path.join(ROOT, "configs")
POLICY_JSON = os.path.join(CONFIGS_DIR, "governance_policy.json")
MARKER = "<!-- POLICY_ADJUST:BEGIN -->"


def load_forecast(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {
            "predicted_drift_probability_pct": 0.0,
            "confidence_pct": 50.0,
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def decide(forecast: Dict[str, Any]) -> Dict[str, Any]:
    drift_prob_pct = float(forecast.get("predicted_drift_probability_pct", 0.0) or 0.0)
    conf_pct = float(forecast.get("confidence_pct", 50.0) or 50.0)
    drift_prob = max(0.0, min(1.0, drift_prob_pct / 100.0))

    if drift_prob > 0.5:
        audit_depth = "full"
        drift_threshold = 0.05
        remediation_note = "Manual remediation trigger: ENABLED"
    elif drift_prob > 0.2:
        audit_depth = "moderate"
        drift_threshold = 0.10
        remediation_note = "Manual remediation trigger: ON-DEMAND"
    else:
        audit_depth = "light"
        drift_threshold = 0.15
        remediation_note = "Manual remediation trigger: STANDBY"

    next_audit = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S UTC")
    policy = {
        "audit_depth": audit_depth,
        "drift_threshold": round(drift_threshold, 4),
        "next_audit_date": next_audit,
        "confidence": round(max(0.0, min(1.0, conf_pct / 100.0)), 2),
    }
    rationale = {
        "drift_probability_pct": round(drift_prob * 100.0, 1),
        "confidence_pct": round(conf_pct, 1),
        "remediation": remediation_note,
    }
    return {"policy": policy, "rationale": rationale}


def write_policy(policy: Dict[str, Any]) -> None:
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    with open(POLICY_JSON, "w", encoding="utf-8") as f:
        json.dump(policy, f, indent=2)


def append_policy_to_summary(r: Dict[str, Any]) -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    lines = []
    if os.path.exists(SUMMARY_MD):
        with open(SUMMARY_MD, "r", encoding="utf-8") as fr:
            lines = fr.read().splitlines()
    # remove any existing POLICY_ADJUST section (from marker to EOF)
    if MARKER in "\n".join(lines):
        idx = [i for i, ln in enumerate(lines) if MARKER in ln]
        if idx:
            lines = lines[: idx[0]]
    # append new section
    policy = r["policy"]
    rationale = r["rationale"]
    block = [
        "",
        MARKER,
        "## Adaptive Governance Policy",
        f"- Audit depth: {policy['audit_depth']}",
        f"- Drift threshold: {policy['drift_threshold']}",
        f"- Next audit date: {policy['next_audit_date']}",
        f"- Confidence: {policy['confidence']}",
        f"- Rationale: drift={rationale['drift_probability_pct']}% | conf={rationale['confidence_pct']}% | {rationale['remediation']}",
    ]
    lines.extend(block)
    with open(SUMMARY_MD, "w", encoding="utf-8") as fw:
        fw.write("\n".join(lines) + "\n")


def main() -> int:
    fc = load_forecast(FORECAST_JSON)
    decision = decide(fc)
    write_policy(decision["policy"])
    append_policy_to_summary(decision)
    # Echo a compact summary for CI logs
    print(json.dumps(decision, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
