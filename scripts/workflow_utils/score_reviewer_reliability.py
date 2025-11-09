#!/usr/bin/env python3
"""
Reviewer Reliability Scoring
- Reads oversight ledger and (optionally) decision trace to compute per-reviewer alignment.
- Writes logs/reviewer_scores.json
- Appends a Reviewer Reliability table to reports/audit_summary.md under REVIEWER_RELIABILITY markers.
"""
from __future__ import annotations
import json
import os
from collections import defaultdict, deque
from statistics import mean
from typing import Dict, Any, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEDGER_JSON = os.path.join(ROOT, "logs", "oversight_ledger.json")
TRACE_JSON = os.path.join(ROOT, "logs", "decision_trace.json")
SCORES_JSON = os.path.join(ROOT, "logs", "reviewer_scores.json")
SUMMARY_MD = os.path.join(ROOT, "reports", "audit_summary.md")
MARKER_BEGIN = "<!-- REVIEWER_RELIABILITY:BEGIN -->"


def _load_list(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def compute_scores(ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Group by reviewer
    stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "reviews_total": 0,
        "reviews_disagreed": 0,
        "alignment": 0.0,
        "trend": [],
    })
    # Track last 5 outcomes for trend per reviewer
    recents: Dict[str, deque] = defaultdict(lambda: deque(maxlen=5))
    for e in ledger:
        reviewer = str(e.get("reviewer") or "Unknown").strip()
        verdict = str(e.get("verdict") or "").lower().strip()
        stats[reviewer]["reviews_total"] += 1
        disagreed = 1 if verdict in {"revised", "rejected"} else 0
        stats[reviewer]["reviews_disagreed"] += disagreed
        align = 1 - (stats[reviewer]["reviews_disagreed"]/stats[reviewer]["reviews_total"])
        stats[reviewer]["alignment"] = round(align, 3)
        recents[reviewer].append(1 - disagreed)  # 1 if aligned, 0 if disagreed
    # finalize trend as rolling average of last 5
    for r, q in recents.items():
        stats[r]["trend"] = round(mean(q), 3) if len(q) > 0 else 0.0
    return stats


def append_table(scores: Dict[str, Any]):
    if not scores:
        return
    os.makedirs(os.path.dirname(SUMMARY_MD), exist_ok=True)
    lines: List[str] = []
    if os.path.exists(SUMMARY_MD):
        with open(SUMMARY_MD, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    # strip prior section
    joined = "\n".join(lines)
    if MARKER_BEGIN in joined:
        idx = [i for i, ln in enumerate(lines) if MARKER_BEGIN in ln]
        if idx:
            lines = lines[:idx[0]]
    block = [
        "",
        MARKER_BEGIN,
        "## Reviewer Reliability",
        "Reviewer | Reviews | Alignment | Trend",
        "----------|----------|-----------|-------",
    ]
    # sort reviewers by total reviews desc
    ordered = sorted(scores.items(), key=lambda kv: kv[1]["reviews_total"], reverse=True)
    for name, s in ordered:
        trend_arrow = "↑" if s.get("trend",0) >= 0.66 else ("→" if s.get("trend",0) >= 0.33 else "↓")
        block.append(f"{name} | {s['reviews_total']} | {s['alignment']:.2f} | {trend_arrow}")
    lines.extend(block)
    with open(SUMMARY_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    ledger = _load_list(LEDGER_JSON)
    scores = compute_scores(ledger)
    os.makedirs(os.path.dirname(SCORES_JSON), exist_ok=True)
    with open(SCORES_JSON, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2)
    append_table(scores)
    print(json.dumps({"reviewers": len(scores)}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
