#!/usr/bin/env python3
"""
Governance Reflex Evaluator

Quantifies the short-term impact of the most recent regime policy action
by computing a Reflex Effectiveness Index (REI) from RSI and GHS deltas.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


AUDIT_MARKER_BEGIN = "<!-- REFLEX_EVALUATION:BEGIN -->"
AUDIT_MARKER_END = "<!-- REFLEX_EVALUATION:END -->"


def load_json(path: str, default: Any = None) -> Any:
    """Load JSON file with fallback default."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default
    except Exception:
        return default


def save_json_atomic(path: str, data: Any) -> None:
    """Atomically write JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def get_last_policy_action(actions_log: list) -> Optional[Dict[str, Any]]:
    """Extract the most recent policy action from log."""
    if not actions_log or not isinstance(actions_log, list):
        return None
    if len(actions_log) == 0:
        return None
    return actions_log[-1]


def get_current_rsi(history: Dict[str, Any]) -> float:
    """Extract current RSI from history."""
    if not history or not isinstance(history, dict):
        return 100.0
    rsi_series = history.get("rsi", [])
    if not rsi_series or not isinstance(rsi_series, list):
        return 100.0
    if len(rsi_series) == 0:
        return 100.0
    last_entry = rsi_series[-1]
    return float(last_entry.get("value", 100.0))


def get_previous_rsi(history: Dict[str, Any]) -> float:
    """Extract previous RSI from history (second to last)."""
    if not history or not isinstance(history, dict):
        return 100.0
    rsi_series = history.get("rsi", [])
    if not rsi_series or not isinstance(rsi_series, list):
        return 100.0
    if len(rsi_series) < 2:
        # No previous, use current as baseline
        return get_current_rsi(history)
    prev_entry = rsi_series[-2]
    return float(prev_entry.get("value", 100.0))


def get_current_ghs(health_report: Dict[str, Any]) -> float:
    """Extract current GHS from governance health report."""
    if not health_report or not isinstance(health_report, dict):
        return 0.0
    return float(health_report.get("GovernanceHealthScore", 0.0))


def get_previous_ghs(policy: Dict[str, Any]) -> float:
    """Extract previous GHS from policy (stored in last action metadata)."""
    if not policy or not isinstance(policy, dict):
        return 0.0
    
    # Check nested governance_policy
    if "governance_policy" in policy:
        gp = policy["governance_policy"]
    else:
        gp = policy
    
    # Look for previous_ghs or fallback to current
    prev = gp.get("previous_ghs")
    if prev is not None:
        return float(prev)
    
    # No previous stored, assume neutral baseline
    return 0.0


def compute_rei(delta_rsi: float, delta_ghs: float) -> float:
    """Compute Reflex Effectiveness Index: 0.7*ΔRSI + 0.3*ΔGHS."""
    return 0.7 * delta_rsi + 0.3 * delta_ghs


def classify_rei(rei: float) -> str:
    """Classify REI into effectiveness categories."""
    if rei > 1.0:
        return "Effective"
    elif rei < -1.0:
        return "Counterproductive"
    else:
        return "Neutral"


def get_classification_emoji(classification: str) -> str:
    """Get emoji for classification."""
    if classification == "Effective":
        return "✅"
    elif classification == "Counterproductive":
        return "⚠️"
    else:
        return "➡️"


def update_audit_summary(
    summary_path: str,
    mode: str,
    delta_rsi: float,
    delta_ghs: float,
    rei: float,
    classification: str
) -> None:
    """Update audit summary with reflex evaluation block (idempotent)."""
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "# Audit Summary\n\n"
    
    emoji = get_classification_emoji(classification)
    block = (
        f"{AUDIT_MARKER_BEGIN}\n"
        f"Reflex Evaluation: Mode {mode}, ΔRSI={delta_rsi:+.1f}, ΔGHS={delta_ghs:+.1f} "
        f"→ {emoji} {classification} (REI={rei:+.2f}).\n"
        f"{AUDIT_MARKER_END}"
    )
    
    # Check if markers exist
    if AUDIT_MARKER_BEGIN in content and AUDIT_MARKER_END in content:
        # Replace existing block
        pattern = re.compile(
            re.escape(AUDIT_MARKER_BEGIN) + r"[\s\S]*?" + re.escape(AUDIT_MARKER_END),
            re.MULTILINE
        )
        content = pattern.sub(block, content)
    else:
        # Append at end
        content = content.rstrip() + "\n\n" + block + "\n"
    
    # Atomic write
    tmp = summary_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, summary_path)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Governance Reflex Evaluator - quantify short-term policy impact"
    )
    parser.add_argument(
        "--actions-log",
        default="logs/regime_policy_actions.json",
        help="Path to regime policy actions log"
    )
    parser.add_argument(
        "--history",
        default="logs/regime_stability_history.json",
        help="Path to regime stability history"
    )
    parser.add_argument(
        "--health",
        default="reports/governance_health.json",
        help="Path to governance health report"
    )
    parser.add_argument(
        "--policy",
        default="configs/governance_policy.json",
        help="Path to governance policy file"
    )
    parser.add_argument(
        "--output",
        default="reports/reflex_evaluation.json",
        help="Path to output evaluation report"
    )
    parser.add_argument(
        "--audit-summary",
        default="reports/audit_summary.md",
        help="Path to audit summary markdown"
    )
    
    args = parser.parse_args(argv)
    
    # Load data
    actions_log = load_json(args.actions_log, [])
    history = load_json(args.history, {})
    health_report = load_json(args.health, {})
    policy = load_json(args.policy, {})
    
    # Get last policy action
    last_action = get_last_policy_action(actions_log)
    if not last_action:
        # First run - no policy action yet, return neutral
        result = {
            "status": "ok",
            "note": "No policy action recorded yet - neutral evaluation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rei": 0.0,
            "classification": "Neutral",
            "delta_rsi": 0.0,
            "delta_ghs": 0.0,
            "policy_mode": "N/A"
        }
        save_json_atomic(args.output, result)
        print(json.dumps(result, indent=2))
        return 0
    
    policy_mode = last_action.get("mode", "Unknown")
    policy_timestamp = last_action.get("timestamp", "")
    
    # Get current and previous values
    current_rsi = get_current_rsi(history)
    previous_rsi = get_previous_rsi(history)
    current_ghs = get_current_ghs(health_report)
    previous_ghs = get_previous_ghs(policy)
    
    # Compute deltas
    delta_rsi = current_rsi - previous_rsi
    delta_ghs = current_ghs - previous_ghs
    
    # Compute REI
    rei = compute_rei(delta_rsi, delta_ghs)
    
    # Classify
    classification = classify_rei(rei)
    
    # Prepare result
    result = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "policy_timestamp": policy_timestamp,
        "policy_mode": policy_mode,
        "current_rsi": current_rsi,
        "previous_rsi": previous_rsi,
        "delta_rsi": round(delta_rsi, 2),
        "current_ghs": current_ghs,
        "previous_ghs": previous_ghs,
        "delta_ghs": round(delta_ghs, 2),
        "rei": round(rei, 2),
        "classification": classification,
    }
    
    # Save result
    save_json_atomic(args.output, result)
    
    # Update audit summary
    update_audit_summary(
        args.audit_summary,
        policy_mode,
        delta_rsi,
        delta_ghs,
        rei,
        classification
    )
    
    # Output summary
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
