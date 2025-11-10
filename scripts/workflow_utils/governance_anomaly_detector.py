#!/usr/bin/env python3
"""Heuristic governance anomaly detector.

The workflow surfaces anomalous governance signals by inspecting recent policy
settings, audit summaries, and drift diagnostics. It emits a JSON report with
ranked anomaly findings for downstream jobs to consume.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = ROOT / "configs"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"
OUTPUT_JSON = ROOT / "governance_anomaly_out.json"

POLICY_JSON = CONFIGS / "governance_policy.json"
AUDIT_SUMMARY_MD = REPORTS / "audit_summary.md"
DRIFT_REPORT_JSON = LOGS / "drift_report.json"


def _load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _to_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_int(pattern: str, text: str) -> int:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def _policy_anomalies(policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(policy, dict):
        return []

    findings: List[Dict[str, Any]] = []

    learning_rate = _to_float(policy.get("learning_rate_factor"), 1.0)
    if learning_rate > 1.6:
        findings.append({
            "type": "adaptation",
            "severity": "high",
            "message": f"Learning rate factor is {learning_rate:.2f} (> 1.6) implying unstable adaptation."}
        )
    elif learning_rate > 1.3:
        findings.append({
            "type": "adaptation",
            "severity": "medium",
            "message": f"Learning rate factor elevated at {learning_rate:.2f}; monitor adaptation volatility."}
        )

    reliability_weight = _to_float(policy.get("reliability_weight"), 1.0)
    if reliability_weight < 0.6:
        findings.append({
            "type": "adaptation",
            "severity": "medium",
            "message": f"Reliability weight degraded to {reliability_weight:.2f} (< 0.60); forecasts are distrusted."}
        )

    drift_threshold = _to_float(policy.get("drift_threshold"), 0.15)
    if drift_threshold > 0.4:
        findings.append({
            "type": "drift",
            "severity": "medium",
            "message": f"Drift threshold relaxed to {drift_threshold:.2f}; coverage may be under-protected."}
        )
    elif 0.0 <= drift_threshold < 0.05:
        findings.append({
            "type": "drift",
            "severity": "low",
            "message": f"Drift threshold tightened to {drift_threshold:.2f}; expect frequent remediations."}
        )

    audit_frequency = str(policy.get("audit_frequency", "7d")).strip().lower()
    days_match = re.match(r"(\d+)(d|day|days)", audit_frequency)
    if days_match:
        days = int(days_match.group(1))
        if days > 14:
            findings.append({
                "type": "governance",
                "severity": "medium",
                "message": f"Audit cadence stretched to every {days} days; oversight window widening."}
            )
    return findings


def _audit_summary_anomalies(summary_text: str) -> List[Dict[str, Any]]:
    if not summary_text:
        return []

    findings: List[Dict[str, Any]] = []

    failed = _parse_int(r"Failed:\s*(\d+)", summary_text)
    if failed >= 3:
        findings.append({
            "type": "compliance",
            "severity": "high",
            "message": f"{failed} failed provenance checks recorded in last audit summary."}
        )
    elif failed > 0:
        findings.append({
            "type": "compliance",
            "severity": "medium",
            "message": f"{failed} provenance checks failed; remediation backlog present."}
        )

    attention_required = bool(re.search(r"ATTENTION REQUIRED", summary_text, re.IGNORECASE))
    if attention_required:
        findings.append({
            "type": "governance",
            "severity": "high",
            "message": "Audit summary marked as ATTENTION REQUIRED; escalate to oversight."}
        )

    backlog = _parse_int(r"Remediated:\s*(\d+)", summary_text)
    if failed > backlog and failed > 0:
        findings.append({
            "type": "compliance",
            "severity": "medium",
            "message": f"{failed - backlog} failed items remain unremediated in audit summary."}
        )

    return findings


def _drift_anomalies(drift_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(drift_report, dict):
        return []

    findings: List[Dict[str, Any]] = []
    overall = _to_float(drift_report.get("overall_drift_rate"), 0.0)
    if overall >= 0.5:
        findings.append({
            "type": "drift",
            "severity": "high",
            "message": f"Overall drift rate at {overall:.2f}; majority of monitored features drifted."}
        )
    elif overall >= 0.2:
        findings.append({
            "type": "drift",
            "severity": "medium",
            "message": f"Overall drift rate at {overall:.2f}; monitor mitigation backlog."}
        )

    features = drift_report.get("features") or drift_report.get("feature_drifts") or {}
    if isinstance(features, dict):
        hot_features = [name for name, meta in features.items() if isinstance(meta, dict) and meta.get("drift")]
        for feature in hot_features[:5]:
            findings.append({
                "type": "drift",
                "severity": "medium",
                "message": f"Feature '{feature}' flagged for drift."}
            )
        if len(hot_features) > 5:
            findings.append({
                "type": "drift",
                "severity": "low",
                "message": f"Additional {len(hot_features) - 5} features show drift (see drift report)."}
            )

    return findings


def detect_anomalies() -> Dict[str, Any]:
    policy = _load_json(POLICY_JSON, {})
    audit_summary = _load_text(AUDIT_SUMMARY_MD)
    drift_report = _load_json(DRIFT_REPORT_JSON, {})

    anomalies: List[Dict[str, Any]] = []
    anomalies.extend(_policy_anomalies(policy))
    anomalies.extend(_audit_summary_anomalies(audit_summary))
    anomalies.extend(_drift_anomalies(drift_report))

    severity_counts = Counter(a.get("severity", "unknown") for a in anomalies)
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "") + "Z"

    return {
        "generated_at": timestamp,
        "anomalies": anomalies,
        "total": len(anomalies),
        "severity_counts": dict(severity_counts)
    }


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    report = detect_anomalies()
    _ensure_parent(OUTPUT_JSON)
    OUTPUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
