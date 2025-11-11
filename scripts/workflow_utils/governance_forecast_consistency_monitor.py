#!/usr/bin/env python3
"""
Forecast Consistency Monitor - Early-Warning Detector for REI-MPI Drift

Purpose: Monitor changes in REI-MPI correlation across consecutive runs to detect
         forecast inconsistency that may indicate drift between policy effectiveness
         and meta-learning quality.

Triggers:
  - Sign change in correlation (positive → negative or vice versa)
  - Correlation drops below -0.4 (divergence threshold)
  - Δcorrelation magnitude > 0.5 (sudden shift)

Outputs: reports/forecast_consistency.json
Updates: audit_summary.md with FORECAST_CONSISTENCY marker
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

AUDIT_MARKER_BEGIN = "<!-- FORECAST_CONSISTENCY:BEGIN -->"
AUDIT_MARKER_END = "<!-- FORECAST_CONSISTENCY:END -->"


def load_json(path: str, default: Any) -> Any:
    """Load JSON file safely."""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: failed to load {path}: {e}", file=sys.stderr)
    return default


def detect_inconsistency(
    prev_corr: float,
    curr_corr: float,
    prev_class: str,
    curr_class: str
) -> Tuple[bool, str, List[str]]:
    """
    Detect forecast consistency issues.
    
    Returns: (is_triggered, status, reasons)
    """
    reasons = []
    triggered = False
    
    # Check for sign change
    if prev_corr * curr_corr < 0:  # Different signs
        reasons.append(f"Sign change detected: {prev_corr:+.3f} → {curr_corr:+.3f}")
        triggered = True
    
    # Check for divergence threshold
    if curr_corr < -0.4:
        reasons.append(f"Correlation below divergence threshold: {curr_corr:+.3f} < -0.4")
        triggered = True
    
    # Check for sudden shift (magnitude change > 0.5)
    delta = abs(curr_corr - prev_corr)
    if delta > 0.5:
        reasons.append(f"Sudden correlation shift: Δ{delta:.3f} > 0.5 threshold")
        triggered = True
    
    # Check for classification deterioration
    deterioration_map = {
        "Aligned improvement": 2,
        "Neutral coupling": 1,
        "Diverging signals": 0
    }
    prev_score = deterioration_map.get(prev_class, 1)
    curr_score = deterioration_map.get(curr_class, 1)
    
    if curr_score < prev_score:
        reasons.append(f"Classification degraded: {prev_class} → {curr_class}")
        triggered = True
    
    if triggered:
        status = "⚠️ Forecast inconsistency detected — possible drift between policy and meta-learning"
    else:
        status = "✅ Forecast consistency maintained — correlation stable"
    
    return triggered, status, reasons


def update_audit_summary(
    summary_path: str,
    status: str,
    prev_corr: float,
    curr_corr: float,
    delta: float,
    triggered: bool
) -> None:
    """Update audit summary with forecast consistency block (idempotent)."""
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "# Audit Summary\n\n"
    
    emoji = "⚠️" if triggered else "✅"
    
    block = (
        f"{AUDIT_MARKER_BEGIN}\n"
        f"Forecast Consistency: {emoji} {status} | "
        f"Correlation {prev_corr:+.3f} → {curr_corr:+.3f} (Δ{delta:+.3f}).\n"
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--alignment",
        default="reports/reflex_forecast_alignment.json",
        help="Path to current forecast alignment JSON"
    )
    parser.add_argument(
        "--history",
        default="logs/forecast_alignment_history.json",
        help="Path to forecast alignment history"
    )
    parser.add_argument(
        "--output",
        default="reports/forecast_consistency.json",
        help="Output path for consistency report"
    )
    parser.add_argument(
        "--audit-summary",
        default="audit_summary.md",
        help="Path to audit summary markdown"
    )
    
    args = parser.parse_args(argv)
    
    # Load current alignment
    current = load_json(args.alignment, {})
    
    # Load history
    history = load_json(args.history, [])
    if not isinstance(history, list):
        history = []
    
    # Extract current correlation
    curr_corr = current.get("rei_mpi_correlation", 0.0)
    curr_class = current.get("classification", "Neutral coupling")
    curr_timestamp = current.get("timestamp", "")
    
    # Get previous alignment from history
    prev_corr = 0.0
    prev_class = "Neutral coupling"
    prev_timestamp = ""
    
    if len(history) > 0:
        last_entry = history[-1]
        prev_corr = last_entry.get("rei_mpi_correlation", 0.0)
        prev_class = last_entry.get("classification", "Neutral coupling")
        prev_timestamp = last_entry.get("timestamp", "")
    
    # Detect inconsistency
    triggered, status, reasons = detect_inconsistency(
        prev_corr, curr_corr, prev_class, curr_class
    )
    
    # Calculate delta
    delta = curr_corr - prev_corr
    
    # Build output
    output = {
        "timestamp": datetime.now().isoformat() + "Z",
        "triggered": triggered,
        "status": status,
        "current_correlation": round(curr_corr, 4),
        "previous_correlation": round(prev_corr, 4),
        "delta_correlation": round(delta, 4),
        "current_classification": curr_class,
        "previous_classification": prev_class,
        "reasons": reasons,
        "severity": "high" if triggered and (curr_corr < -0.4 or abs(delta) > 0.7) else "medium" if triggered else "low"
    }
    
    # Write output
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    
    # Update history (append current alignment)
    if current:
        history.append({
            "timestamp": curr_timestamp,
            "rei_mpi_correlation": curr_corr,
            "classification": curr_class,
            "n_samples": current.get("n_samples", 0)
        })
        
        # Keep last 20 entries
        if len(history) > 20:
            history = history[-20:]
        
        os.makedirs(os.path.dirname(args.history), exist_ok=True)
        with open(args.history, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    
    # Update audit summary
    update_audit_summary(
        args.audit_summary,
        status,
        prev_corr,
        curr_corr,
        delta,
        triggered
    )
    
    # Print summary
    result = {
        "status": "ok",
        "triggered": triggered,
        "consistency_status": status,
        "delta_correlation": round(delta, 4),
        "severity": output["severity"],
        "output": args.output
    }
    
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
