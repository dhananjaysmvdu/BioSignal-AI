#!/usr/bin/env python3
"""
governance_meta_feedback_controller.py

Adaptive Meta-Feedback Coupling Controller

Purpose:
- Automatically tune learning rate and audit cadence based on MPI
- Close the feedback loop: meta-performance influences system parameters
- Enable self-correcting behavior when learning degrades

Classification Rules:
- MPI < 60 (Critical): Reduce learning rate 20%, double audit frequency
- 60 ≤ MPI < 80 (Caution): Reduce learning rate 10%, increase audit freq 25%
- MPI ≥ 80 (Stable): Increase learning rate 5% (capped at 1.5x), maintain freq

Outputs:
- reports/meta_feedback_actions.json (parameter adjustments)
- Updates audit summary block META_FEEDBACK
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


AUDIT_MARKER_BEGIN = "<!-- META_FEEDBACK:BEGIN -->"
AUDIT_MARKER_END = "<!-- META_FEEDBACK:END -->"


def load_json(path: Path, default: Any = None) -> Any:
    """Load JSON file with fallback."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def compute_adjustments(
    mpi: float,
    current_lr_factor: float,
    current_audit_freq: int
) -> Dict[str, Any]:
    """
    Compute parameter adjustments based on MPI classification.
    
    Args:
        mpi: Meta-Performance Index [0-100+]
        current_lr_factor: Current learning rate multiplier
        current_audit_freq: Current audit frequency in days
        
    Returns:
        Dictionary with new parameters and classification
    """
    # Classification
    if mpi < 60:
        status = "critical"
        lr_multiplier = 0.8
        audit_multiplier = 0.5  # Double frequency = half the days
        reason = "Learning degradation detected — reducing learning rate, increasing audit frequency"
    elif mpi < 80:
        status = "caution"
        lr_multiplier = 0.9
        audit_multiplier = 0.75
        reason = "Mild drift detected — moderately reducing learning rate, increasing audit frequency"
    else:
        status = "stable"
        lr_multiplier = 1.05
        audit_multiplier = 1.0  # Maintain frequency
        reason = "Stable learning — slightly increasing learning rate"
    
    # Compute new values
    new_lr_factor = current_lr_factor * lr_multiplier
    new_audit_freq = round(current_audit_freq * audit_multiplier)
    
    # Apply bounds
    new_lr_factor = max(0.1, min(new_lr_factor, 1.5))  # Clamp [0.1, 1.5]
    new_audit_freq = max(3, new_audit_freq)  # Minimum 3 days
    
    # Compute deltas
    lr_delta = new_lr_factor - current_lr_factor
    audit_delta = new_audit_freq - current_audit_freq
    
    return {
        "status": status,
        "reason": reason,
        "learning_rate_factor": {
            "previous": current_lr_factor,
            "new": new_lr_factor,
            "delta": lr_delta,
            "multiplier": lr_multiplier
        },
        "audit_frequency_days": {
            "previous": current_audit_freq,
            "new": new_audit_freq,
            "delta": audit_delta,
            "multiplier": audit_multiplier
        }
    }


def update_audit_summary(
    summary_path: Path,
    mpi: float,
    status: str,
    lr_delta: float,
    audit_delta: int
) -> None:
    """Update audit summary with meta-feedback block (idempotent)."""
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "# Audit Summary\n\n"
    
    # Status emoji
    if status == "critical":
        emoji = "🔴"
    elif status == "caution":
        emoji = "🟡"
    else:
        emoji = "🟢"
    
    block = (
        f"{AUDIT_MARKER_BEGIN}\n"
        f"Meta-Feedback: MPI={mpi:.1f}% {emoji} {status} | "
        f"Learning rate Δ{lr_delta:+.3f}, Audit freq Δ{audit_delta:+d} days.\n"
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
    tmp = str(summary_path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, summary_path)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Governance Meta-Feedback Controller - adaptive parameter tuning based on MPI"
    )
    parser.add_argument(
        "--meta-performance",
        type=Path,
        default=Path("reports/reflex_meta_performance.json"),
        help="Path to meta-performance report"
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("reports/governance_policy.json"),
        help="Path to governance policy report"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/meta_feedback_actions.json"),
        help="Path to output meta-feedback actions JSON"
    )
    parser.add_argument(
        "--audit-summary",
        type=Path,
        default=Path("reports/audit_summary.md"),
        help="Path to audit summary markdown"
    )
    
    args = parser.parse_args(argv)
    
    # Load meta-performance
    meta_perf = load_json(args.meta_performance, {})
    if not meta_perf or meta_perf.get("status") != "ok":
        print(json.dumps({
            "status": "skip",
            "reason": "No valid meta-performance data available"
        }, indent=2))
        return 0
    
    mpi = meta_perf.get("mpi", 0.0)
    classification = meta_perf.get("classification", "Unknown")
    
    # Load policy for current parameters
    policy = load_json(args.policy, {})
    current_lr_factor = policy.get("learning_rate_factor", 1.0)
    current_audit_freq = policy.get("audit_frequency_days", 14)
    
    # Compute adjustments
    adjustments = compute_adjustments(mpi, current_lr_factor, current_audit_freq)
    
    # Build output
    result = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mpi": mpi,
        "mpi_classification": classification,
        "meta_feedback_status": adjustments["status"],
        "reason": adjustments["reason"],
        "adjustments": adjustments
    }
    
    # Write output
    os.makedirs(args.output.parent, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    
    # Update audit summary
    update_audit_summary(
        args.audit_summary,
        mpi,
        adjustments["status"],
        adjustments["learning_rate_factor"]["delta"],
        adjustments["audit_frequency_days"]["delta"]
    )
    
    # Print summary
    print(json.dumps({
        "status": "ok",
        "meta_feedback_status": adjustments["status"],
        "mpi": mpi,
        "learning_rate_delta": adjustments["learning_rate_factor"]["delta"],
        "audit_frequency_delta": adjustments["audit_frequency_days"]["delta"]
    }, indent=2))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
