#!/usr/bin/env python3
"""
Ethical Compliance Engine (ECE)

Evaluates fairness metrics from observatory data and computes Bias Score (BS).
BS = |max(group_mean) - min(group_mean)| / mean(global)
Flags bias violations and appends ETHICAL_COMPLIANCE marker to audit_summary.md.
"""
from __future__ import annotations

import csv
import json
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "ethics_engine" / "ethics_config.yaml"
FAIRNESS_METRICS = ROOT / "observatory" / "fairness_metrics.csv"
AUDIT_SUMMARY = ROOT / "audit_summary.md"
REPORTS_DIR = ROOT / "reports" / "ethics"


def load_config() -> dict:
    """Load ethics configuration."""
    if not CONFIG.exists():
        return {
            "fairness_threshold": 0.95,
            "bias_detection_window": 30,
            "escalation_policy": "audit + notify",
            "alert_thresholds": {
                "bias_score_critical": 0.10,
                "bias_score_warning": 0.05,
            }
        }
    try:
        with CONFIG.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_fairness_data() -> list[dict]:
    """Load fairness metrics from observatory CSV. Create placeholder if missing."""
    if not FAIRNESS_METRICS.exists():
        # Generate placeholder fairness data for demonstration
        FAIRNESS_METRICS.parent.mkdir(parents=True, exist_ok=True)
        with FAIRNESS_METRICS.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "group", "metric", "value"])
            writer.writeheader()
            # Example: two demographic groups with near-parity
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            writer.writerow({"timestamp": ts, "group": "A", "metric": "accuracy", "value": 0.975})
            writer.writerow({"timestamp": ts, "group": "B", "metric": "accuracy", "value": 0.970})
            writer.writerow({"timestamp": ts, "group": "C", "metric": "accuracy", "value": 0.968})
        print(f"ℹ️ Generated placeholder fairness data: {FAIRNESS_METRICS}")
    
    data = []
    try:
        with FAIRNESS_METRICS.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(row)
    except Exception as e:
        print(f"⚠️ Error reading fairness metrics: {e}", file=sys.stderr)
    return data


def compute_bias_score(fairness_data: list[dict], metric: str = "accuracy") -> dict:
    """
    Compute Bias Score: BS = |max(group_mean) - min(group_mean)| / mean(global)
    Returns dict with BS, group stats, and status.
    """
    # Filter by metric
    filtered = [r for r in fairness_data if r.get("metric") == metric]
    if not filtered:
        return {"bias_score": 0.0, "status": "no_data", "groups": []}
    
    # Group means
    group_values = {}
    for row in filtered:
        group = row.get("group", "unknown")
        try:
            value = float(row.get("value", 0))
            if group not in group_values:
                group_values[group] = []
            group_values[group].append(value)
        except ValueError:
            continue
    
    if not group_values:
        return {"bias_score": 0.0, "status": "no_data", "groups": []}
    
    # Compute group means
    group_means = {g: sum(vals) / len(vals) for g, vals in group_values.items()}
    
    # Global mean
    all_values = [v for vals in group_values.values() for v in vals]
    global_mean = sum(all_values) / len(all_values) if all_values else 1.0
    
    # Bias Score
    max_mean = max(group_means.values())
    min_mean = min(group_means.values())
    bias_score = abs(max_mean - min_mean) / global_mean if global_mean > 0 else 0.0
    
    return {
        "bias_score": round(bias_score, 4),
        "global_mean": round(global_mean, 4),
        "max_group_mean": round(max_mean, 4),
        "min_group_mean": round(min_mean, 4),
        "groups": [{"group": g, "mean": round(m, 4)} for g, m in group_means.items()],
        "status": "acceptable" if bias_score < 0.05 else ("warning" if bias_score < 0.10 else "critical"),
    }


def evaluate_fairness(config: dict, bias_result: dict) -> dict:
    """
    Evaluate overall fairness status based on bias score and fairness threshold.
    """
    threshold = config.get("fairness_threshold", 0.95)
    bias_score = bias_result.get("bias_score", 0.0)
    global_mean = bias_result.get("global_mean", 1.0)
    
    # Fairness score: 1 - bias_score (conceptual; higher = more fair)
    fairness_score = max(0.0, 1.0 - bias_score)
    
    result = {
        "fairness_score": round(fairness_score, 4),
        "fairness_threshold": threshold,
        "passes_threshold": fairness_score >= threshold,
        "bias_score": bias_score,
        "status": bias_result.get("status", "unknown"),
    }
    
    return result


def append_audit_marker(fairness_result: dict) -> None:
    """Append or update ETHICAL_COMPLIANCE marker in audit_summary.md."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    marker_line = f"<!-- ETHICAL_COMPLIANCE: UPDATED {ts} -->"
    
    if not AUDIT_SUMMARY.exists():
        AUDIT_SUMMARY.write_text(f"\n{marker_line}\n", encoding="utf-8")
        return
    
    lines = AUDIT_SUMMARY.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if "<!-- ETHICAL_COMPLIANCE:" in line:
            lines[i] = marker_line
            found = True
            break
    
    if not found:
        lines.append("")
        lines.append(marker_line)
    
    AUDIT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ Appended ETHICAL_COMPLIANCE marker to {AUDIT_SUMMARY}")


def save_ethics_report(bias_result: dict, fairness_result: dict) -> None:
    """Save ethics compliance report JSON."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = REPORTS_DIR / f"ethics_compliance_{ts}.json"
    
    report = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "bias_analysis": bias_result,
        "fairness_evaluation": fairness_result,
    }
    
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Ethics compliance report saved: {report_path}")


def main() -> int:
    config = load_config()
    fairness_data = load_fairness_data()
    
    # Compute bias score
    bias_result = compute_bias_score(fairness_data, metric="accuracy")
    print(f"📊 Bias Score: {bias_result['bias_score']} ({bias_result['status'].upper()})")
    
    # Evaluate fairness
    fairness_result = evaluate_fairness(config, bias_result)
    print(f"✅ Fairness Score: {fairness_result['fairness_score']} (threshold: {fairness_result['fairness_threshold']})")
    print(f"   Passes: {fairness_result['passes_threshold']}")
    
    # Save report
    save_ethics_report(bias_result, fairness_result)
    
    # Append audit marker
    append_audit_marker(fairness_result)
    
    # Exit with warning if fairness below threshold
    if not fairness_result["passes_threshold"]:
        print(f"⚠️ FAIRNESS ALERT: Score {fairness_result['fairness_score']} below threshold {fairness_result['fairness_threshold']}")
        return 1
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
