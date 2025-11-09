#!/usr/bin/env python3
"""
Meta-Learning Layer for Adaptive Governance
- Reads oversight ledger, decision trace, and governance policy.
- Computes reviewer disagreement rate, mean confidence, frequency of post-review policy adjustments.
- Adjusts learning coefficients in governance_policy.json.
- Appends META_LEARNING block to reports/audit_summary.md.
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEDGER_JSON = os.path.join(ROOT, "logs", "oversight_ledger.json")
TRACE_JSON = os.path.join(ROOT, "logs", "decision_trace.json")
POLICY_JSON = os.path.join(ROOT, "configs", "governance_policy.json")
SUMMARY_MD = os.path.join(ROOT, "reports", "audit_summary.md")
META_MARKER = "<!-- META_LEARNING:BEGIN -->"


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


def _load_policy() -> Dict[str, Any]:
    if not os.path.exists(POLICY_JSON):
        return {}
    try:
        with open(POLICY_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def compute_metrics(ledger: List[Dict[str, Any]], trace: List[Dict[str, Any]]) -> Dict[str, float]:
    total_reviews = len(ledger)
    if total_reviews == 0:
        return {
            "disagreement_rate": 0.0,
            "mean_confidence": 0.0,
            "post_review_adjust_rate": 0.0,
        }
    revised = sum(1 for e in ledger if e.get("verdict") == "revised")
    rejected = sum(1 for e in ledger if e.get("verdict") == "rejected")
    disagreement_rate = (revised + rejected) / total_reviews
    # mean confidence from decision trace entries near review times
    # fallback: average of inputs.confidence across trace entries
    confidences = [float(d.get("inputs", {}).get("confidence", 0.0)) for d in trace if isinstance(d.get("inputs"), dict)]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    # post-review policy adjustments: count decisions classified as increase or revised after a review verdict not approved
    adjustment_actions = sum(1 for d in trace if str(d.get("decision","")) in {"increase_audit_depth", "state_transition"})
    post_review_adjust_rate = adjustment_actions / max(1, len(trace))
    return {
        "disagreement_rate": disagreement_rate,
        "mean_confidence": mean_confidence,
        "post_review_adjust_rate": post_review_adjust_rate,
    }


def adjust_policy(policy: Dict[str, Any], metrics: Dict[str, float]) -> Dict[str, Any]:
    lc = policy.get("learning_coefficients", {
        "confidence_weight": 0.5,
        "drift_weight": 0.5,
        "human_feedback_weight": 0.5,
    })
    # update human_feedback_weight based on disagreement rate (bounded 0.3..0.9)
    dr = metrics.get("disagreement_rate", 0.0)
    hf_weight = min(0.9, max(0.3, 0.5 + (dr - 0.1)))  # baseline 0.5; raise if dr>0.1
    lc["human_feedback_weight"] = round(hf_weight, 3)
    # confidence weight decays slightly if high disagreement
    lc["confidence_weight"] = round(max(0.3, 0.6 - dr * 0.2), 3)
    # drift weight complementary balance
    lc["drift_weight"] = round(max(0.3, 1.0 - lc["confidence_weight"]), 3)

    # option: adjust an internal confidence threshold if present
    conf_thresh = policy.get("confidence_threshold", 0.75)
    if hf_weight > 0.6:  # more human feedback emphasis -> lower threshold slightly
        conf_thresh = max(0.5, conf_thresh - 0.05)
    policy["confidence_threshold"] = round(conf_thresh, 2)
    policy["learning_coefficients"] = lc
    return policy


def append_meta_block(metrics: Dict[str, float], policy: Dict[str, Any]):
    os.makedirs(os.path.dirname(SUMMARY_MD), exist_ok=True)
    lines: List[str] = []
    if os.path.exists(SUMMARY_MD):
        with open(SUMMARY_MD, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    joined = "\n".join(lines)
    if META_MARKER in joined:
        idx = [i for i, ln in enumerate(lines) if META_MARKER in ln]
        if idx:
            lines = lines[:idx[0]]
    block = [
        "",
        META_MARKER,
        "## Human Feedback Integration",
        f"Disagreement Rate: {metrics.get('disagreement_rate',0.0)*100:.1f}%",
        f"Adjusted Confidence Threshold: {policy.get('confidence_threshold',0):.2f}",
        f"Feedback Weight: {policy.get('learning_coefficients',{}).get('human_feedback_weight',0):.3f}",
    ]
    lines.extend(block)
    with open(SUMMARY_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    ledger = _load_list(LEDGER_JSON)
    trace = _load_list(TRACE_JSON)
    policy = _load_policy()
    metrics = compute_metrics(ledger, trace)
    policy = adjust_policy(policy, metrics)
    # persist updated policy
    os.makedirs(os.path.dirname(POLICY_JSON), exist_ok=True)
    with open(POLICY_JSON, "w", encoding="utf-8") as f:
        json.dump(policy, f, indent=2)
    append_meta_block(metrics, policy)
    print(json.dumps({"metrics": metrics, "policy": policy}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
