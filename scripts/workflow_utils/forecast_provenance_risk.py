#!/usr/bin/env python3
"""
Forecast provenance risk using simple statistics over historical audits.
- Reads reports/history/versions.json (optional) and reports/audit_summary*.md files
- Extracts features: pass/fail counts, drift rate (failed/checked), remediation count, (optional) duration
- Uses EMA to forecast next drift probability and remediation load; computes a heuristic confidence
- Writes JSON to reports/provenance_forecast.json
- Appends a compact Markdown forecast table to reports/audit_summary.md

No external deps.
"""
from __future__ import annotations
import os
import re
import json
from glob import glob
from datetime import datetime, timezone
from statistics import mean, pstdev

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORTS_DIR = os.path.join(ROOT, "reports")
HISTORY_JSON = os.path.join(ROOT, "reports", "history", "versions.json")
SUMMARY_MD = os.path.join(REPORTS_DIR, "audit_summary.md")

MD_LINE = re.compile(r"^\s*-\s*([^:]+):\s*(.*)$")
KEY_MAP = {
    "Timestamp": "timestamp",
    "Auditor": "auditor",
    "Commits checked": "checked",
    "Checked": "checked",
    "Passed": "passed",
    "Failed": "failed",
    "Remediated": "remediated",
    "Issue": "issue",
    "Workflow": "workflow",
    "Overall Status": "status",
    "Duration": "duration",
}


def parse_summary_md(path: str) -> dict:
    data: dict = {}
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = MD_LINE.match(line.strip())
            if not m:
                continue
            k, v = m.group(1).strip(), m.group(2).strip()
            k = KEY_MAP.get(k, k)
            data[k] = v
    # coerce ints
    for k in ("checked", "passed", "failed", "remediated"):
        if k in data:
            try:
                data[k] = int(re.findall(r"\d+", str(data[k]))[0])
            except Exception:
                try:
                    data[k] = int(data[k])
                except Exception:
                    data[k] = 0
    return data


def collect_runs() -> list[dict]:
    paths = []
    main = SUMMARY_MD
    if os.path.exists(main):
        paths.append(main)
    paths.extend(sorted(glob(os.path.join(REPORTS_DIR, "audit_summary*.md"))))
    # de-dup preserving order
    seen = set()
    uniq = []
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    runs = [parse_summary_md(p) | {"_path": os.path.relpath(p, ROOT)} for p in uniq if os.path.exists(p)]
    return runs


def ema(series: list[float], alpha: float) -> float:
    if not series:
        return 0.0
    v = series[0]
    for x in series[1:]:
        v = alpha * x + (1 - alpha) * v
    return v


def forecast(window: int = 10) -> dict:
    runs = collect_runs()
    if not runs:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "updated_at": now,
            "window": window,
            "predicted_drift_probability_pct": 0.0,
            "expected_remediations": 0,
            "confidence_pct": 50.0,
            "note": "No runs found",
        }
    last = runs[-window:]
    drift = []
    rem = []
    for r in last:
        checked = int(r.get("checked", 0) or 0)
        failed = int(r.get("failed", 0) or 0)
        remediated = int(r.get("remediated", 0) or 0)
        rate = (failed / checked) if checked else 0.0
        drift.append(rate)
        rem.append(remediated)
    n = len(last)
    alpha = 2.0 / (min(n, window) + 1.0)
    pred_drift = ema(drift, alpha) if drift else 0.0
    pred_rem = ema(rem, alpha) if rem else 0.0

    # Confidence heuristic based on series variability and sample size
    if n >= 3 and any(drift):
        m = mean(drift)
        sd = pstdev(drift) if len(drift) > 1 else 0.0
        cv = (sd / m) if m > 0 else 1.0
        base = max(0.0, 1.0 - min(cv, 1.0))  # 0..1
        size = min(1.0, n / window)
        conf = 50.0 + 45.0 * base * size
    else:
        conf = 55.0 if n >= 2 else 50.0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {
        "updated_at": now,
        "window": window,
        "predicted_drift_probability_pct": round(max(0.0, min(1.0, pred_drift)) * 100.0, 1),
        "expected_remediations": int(round(max(0.0, pred_rem))),
        "confidence_pct": round(max(0.0, min(100.0, conf)), 1),
        "series": {
            "drift": drift,
            "remediations": rem,
        },
    }
    return out


def append_markdown_forecast(md_path: str, f: dict) -> None:
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    lines = []
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as fr:
            lines = fr.read().splitlines()
    # Append compact table
    table = [
        "",
        "## Forecast (Next Run)",
        "Metric | Predicted Value | Confidence",
        "---|---:|---:",
        f"Drift Probability | {f.get('predicted_drift_probability_pct', 0)}% | {f.get('confidence_pct', 0)}%",
        f"Expected Remediations | {f.get('expected_remediations', 0)} | {f.get('confidence_pct', 0)}%",
    ]
    lines.extend(table)
    with open(md_path, "w", encoding="utf-8") as fw:
        fw.write("\n".join(lines) + "\n")


def main() -> int:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    result = forecast(window=10)
    out_json = os.path.join(REPORTS_DIR, "provenance_forecast.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    append_markdown_forecast(SUMMARY_MD, result)
    print(json.dumps(result))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
