#!/usr/bin/env python3
"""
Autonomous Ethics Report Generator

Aggregates:
- Bias trends from observatory/fairness_metrics.csv and reports/ethics/
- Decision traces from exports/decision_trace_log.jsonl
- Meta-audit results from meta_audit/meta_audit_log.jsonl

Generates quarterly report: reports/ethics_compliance_Q2_2026.json
(PDF generation requires additional libraries; JSON for now)
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
FAIRNESS_CSV = ROOT / "observatory" / "fairness_metrics.csv"
ETHICS_REPORTS_DIR = ROOT / "reports" / "ethics"
DECISION_TRACE = ROOT / "exports" / "decision_trace_log.jsonl"
META_AUDIT_LOG = ROOT / "meta_audit" / "meta_audit_log.jsonl"
AUDIT_SUMMARY = ROOT / "audit_summary.md"

OUTPUT_DIR = ROOT / "reports"


def load_bias_trends() -> list[dict]:
    """Load recent bias trends from ethics reports."""
    if not ETHICS_REPORTS_DIR.exists():
        return []
    
    trends = []
    for report_file in sorted(ETHICS_REPORTS_DIR.glob("ethics_compliance_*.json")):
        try:
            data = json.loads(report_file.read_text(encoding="utf-8"))
            trends.append({
                "date": data.get("timestamp", "unknown"),
                "bias_score": data.get("bias_analysis", {}).get("bias_score"),
                "fairness_score": data.get("fairness_evaluation", {}).get("fairness_score"),
                "status": data.get("bias_analysis", {}).get("status"),
            })
        except Exception:
            continue
    return trends


def load_decision_traces(limit: int = 10) -> list[dict]:
    """Load latest decision traces."""
    if not DECISION_TRACE.exists():
        return []
    
    traces = []
    try:
        with DECISION_TRACE.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    traces.append(json.loads(line))
    except Exception:
        pass
    return traces[-limit:]


def load_meta_audit_summary() -> dict:
    """Load latest meta-audit results."""
    if not META_AUDIT_LOG.exists():
        return {"status": "no_data", "runs": 0}
    
    try:
        with META_AUDIT_LOG.open("r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
            if not lines:
                return {"status": "no_data", "runs": 0}
            last_entry = json.loads(lines[-1])
            return {
                "status": "available",
                "runs": len(lines),
                "latest_timestamp": last_entry.get("timestamp"),
                "drift": last_entry.get("drift", {}),
            }
    except Exception:
        return {"status": "error", "runs": 0}


def compute_report_hash(report: dict) -> str:
    """Compute SHA-256 hash of report for integrity verification."""
    content = json.dumps(report, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def append_ethics_report_marker() -> None:
    """Append ETHICS_REPORT marker to audit_summary.md."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    marker_line = f"<!-- ETHICS_REPORT: GENERATED {ts} -->"
    
    if not AUDIT_SUMMARY.exists():
        AUDIT_SUMMARY.write_text(f"\n{marker_line}\n", encoding="utf-8")
        return
    
    lines = AUDIT_SUMMARY.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if "<!-- ETHICS_REPORT:" in line:
            lines[i] = marker_line
            found = True
            break
    
    if not found:
        lines.append("")
        lines.append(marker_line)
    
    AUDIT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ Appended ETHICS_REPORT marker to {AUDIT_SUMMARY}")


def generate_report(period: str = "Q2_2026") -> None:
    """Generate comprehensive ethics compliance report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    bias_trends = load_bias_trends()
    decision_traces = load_decision_traces(limit=10)
    meta_audit = load_meta_audit_summary()
    
    report = {
        "report_id": f"ETHICS_{period}",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "period": period,
        "summary": {
            "total_bias_evaluations": len(bias_trends),
            "latest_bias_score": bias_trends[-1]["bias_score"] if bias_trends else None,
            "latest_fairness_score": bias_trends[-1]["fairness_score"] if bias_trends else None,
            "governance_decisions_logged": len(decision_traces),
            "meta_audit_runs": meta_audit.get("runs", 0),
        },
        "bias_trends": bias_trends,
        "decision_traces": decision_traces,
        "meta_audit_summary": meta_audit,
        "compliance_status": "CERTIFIED" if (bias_trends and bias_trends[-1]["bias_score"] < 0.05) else "UNDER_REVIEW",
    }
    
    report["report_hash"] = compute_report_hash(report)
    
    output_path = OUTPUT_DIR / f"ethics_compliance_{period}.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Ethics compliance report generated: {output_path}")
    print(f"   Report Hash (SHA-256): {report['report_hash']}")
    
    # Append audit marker
    append_ethics_report_marker()


def main() -> None:
    period = sys.argv[1] if len(sys.argv) > 1 else "Q2_2026"
    generate_report(period)


if __name__ == "__main__":
    main()
