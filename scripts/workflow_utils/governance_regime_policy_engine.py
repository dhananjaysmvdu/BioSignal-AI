#!/usr/bin/env python3
"""
Governance Regime Policy Engine

Translates regime stability alerts (RSI) into controlled governance adjustments.
Implements meta-feedback loop for adaptive governance parameter tuning.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


AUDIT_MARKER_BEGIN = "<!-- REGIME_POLICY:BEGIN -->"
AUDIT_MARKER_END = "<!-- REGIME_POLICY:END -->"


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


def compute_rsi_trend(history: list[dict]) -> str:
    """Compute RSI trend from history (increasing, decreasing, stable)."""
    if len(history) < 2:
        return "stable"
    recent = history[-5:]  # last 5 entries
    values = [float(e.get("value", 0)) for e in recent if "value" in e]
    if len(values) < 2:
        return "stable"
    # Simple linear trend
    diffs = [values[i] - values[i-1] for i in range(1, len(values))]
    avg_diff = sum(diffs) / len(diffs)
    if avg_diff > 1.0:
        return "increasing"
    elif avg_diff < -1.0:
        return "decreasing"
    return "stable"


def classify_rsi(rsi: float) -> str:
    """Classify RSI into category."""
    if rsi < 50:
        return "critical"
    elif rsi < 80:
        return "caution"
    else:
        return "normal"


def apply_policy_rules(
    rsi: float,
    trend: str,
    current_policy: Dict[str, Any]
) -> Dict[str, Any]:
    """Apply policy adjustment rules based on RSI and trend."""
    category = classify_rsi(rsi)
    
    # Extract current values with defaults
    learning_rate = float(current_policy.get("learning_rate_factor", 1.0))
    audit_freq = int(current_policy.get("audit_frequency_days", 7))
    stab_mode = current_policy.get("stabilization_mode", "monitor")
    
    adjustments = {}
    mode = "Normal Operation"
    
    if category == "critical" and trend == "decreasing":
        # Critical Intervention
        mode = "Critical Intervention"
        new_lr = learning_rate * 0.8
        new_freq = max(3, audit_freq // 2)
        new_stab = "active"
        adjustments = {
            "learning_rate_factor": round(new_lr, 4),
            "audit_frequency_days": new_freq,
            "stabilization_mode": new_stab,
        }
    elif category == "critical" or category == "caution":
        # Caution Mode (includes critical with non-decreasing trend)
        mode = "Caution Mode"
        new_lr = learning_rate * 0.9
        new_freq = max(3, round(audit_freq * 0.75))
        new_stab = "monitor"
        adjustments = {
            "learning_rate_factor": round(new_lr, 4),
            "audit_frequency_days": new_freq,
            "stabilization_mode": new_stab,
        }
    else:
        # Normal Operation
        mode = "Normal Operation"
        new_lr = min(learning_rate * 1.2, 1.5)
        new_stab = "adaptive"
        adjustments = {
            "learning_rate_factor": round(new_lr, 4),
            "stabilization_mode": new_stab,
        }
        # Keep audit frequency unchanged in normal mode
        adjustments["audit_frequency_days"] = audit_freq
    
    # Add metadata
    adjustments["policy_action"] = {
        "mode": mode,
        "rsi": rsi,
        "trend": trend,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    return adjustments


def update_audit_summary(
    summary_path: str,
    mode: str,
    lr_factor: float,
    audit_freq: int
) -> None:
    """Update audit summary with regime policy block (idempotent)."""
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "# Audit Summary\n\n"
    
    block = (
        f"{AUDIT_MARKER_BEGIN}\n"
        f"🧭 Regime policy applied — mode: {mode}, "
        f"learning_rate_factor: {lr_factor}, "
        f"audit_freq: {audit_freq}d.\n"
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
        description="Governance Regime Policy Engine - translate RSI into policy adjustments"
    )
    parser.add_argument(
        "--current",
        default="reports/regime_stability.json",
        help="Path to current regime stability report"
    )
    parser.add_argument(
        "--history",
        default="logs/regime_stability_history.json",
        help="Path to regime stability history log"
    )
    parser.add_argument(
        "--policy",
        default="configs/governance_policy.json",
        help="Path to governance policy file"
    )
    parser.add_argument(
        "--actions-log",
        default="logs/regime_policy_actions.json",
        help="Path to policy actions log"
    )
    parser.add_argument(
        "--audit-summary",
        default="reports/audit_summary.md",
        help="Path to audit summary markdown"
    )
    
    args = parser.parse_args(argv)
    
    # Load current RSI
    current = load_json(args.current, {})
    rsi = float(current.get("stability_index") or current.get("rsi") or 100.0)
    
    # Load history for trend analysis
    history = load_json(args.history, {})
    hist_series = []
    if isinstance(history, dict) and isinstance(history.get("rsi"), list):
        hist_series = history["rsi"]
    
    trend = compute_rsi_trend(hist_series)
    
    # Load current policy
    policy_data = load_json(args.policy, {})
    if not policy_data:
        # Initialize minimal policy
        policy_data = {
            "governance_policy": {
                "learning_rate_factor": 1.0,
                "audit_frequency_days": 7,
                "stabilization_mode": "monitor",
            }
        }
    
    # Get nested policy object or use top-level
    if "governance_policy" in policy_data:
        current_policy = policy_data["governance_policy"]
    else:
        current_policy = policy_data
    
    # Apply policy rules
    adjustments = apply_policy_rules(rsi, trend, current_policy)
    
    # Update policy
    current_policy.update(adjustments)
    
    # If nested, update the nested object
    if "governance_policy" in policy_data:
        policy_data["governance_policy"] = current_policy
    else:
        policy_data = current_policy
    
    # Save updated policy
    save_json_atomic(args.policy, policy_data)
    
    # Append to actions log
    actions_log = load_json(args.actions_log, [])
    if not isinstance(actions_log, list):
        actions_log = []
    
    action_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rsi": rsi,
        "trend": trend,
        "mode": adjustments["policy_action"]["mode"],
        "adjustments": {
            k: v for k, v in adjustments.items() 
            if k != "policy_action"
        }
    }
    actions_log.append(action_entry)
    save_json_atomic(args.actions_log, actions_log)
    
    # Update audit summary
    mode = adjustments["policy_action"]["mode"]
    lr_factor = adjustments["learning_rate_factor"]
    audit_freq = adjustments["audit_frequency_days"]
    
    update_audit_summary(args.audit_summary, mode, lr_factor, audit_freq)
    
    # Output summary
    result = {
        "status": "ok",
        "mode": mode,
        "rsi": rsi,
        "trend": trend,
        "learning_rate_factor": lr_factor,
        "audit_frequency_days": audit_freq,
        "stabilization_mode": adjustments["stabilization_mode"],
    }
    
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
