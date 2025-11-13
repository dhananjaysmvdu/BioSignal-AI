#!/usr/bin/env python3
"""
Governance Reflex Reinforcement Index (RRI) Evaluator

Quantifies how much confidence-weighted adaptation improved performance over time.

RRI = 100 × (0.5×ΔR² + 0.3×ΔMPI + 0.2×ΔLR)

Classifications:
  RRI ≥ +10:     🟢 Reinforcing (adaptation improved learning outcomes)
  -10 ≤ RRI < +10: 🟡 Neutral (little measurable impact)
  RRI < -10:     🔴 Counterproductive (adaptation degraded meta-performance)

Inputs:
  - logs/reflex_model_history.json (R² history)
  - reports/confidence_adaptation.json (learning rate adjustments)
  - reports/reflex_meta_performance.json (MPI scores)

Outputs:
  - reports/reflex_reinforcement.json
  - reports/audit_summary.md (REFLEX_REINFORCEMENT marker)
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


AUDIT_MARKER_BEGIN = "<!-- REFLEX_REINFORCEMENT:BEGIN -->"
AUDIT_MARKER_END = "<!-- REFLEX_REINFORCEMENT:END -->"


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


def save_json(path: str, data: Any) -> None:
    """Save data to JSON file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def update_audit_summary(
    audit_path: str,
    rri: float,
    classification: str,
    emoji: str,
    delta_r2: float,
    delta_mpi: float,
    delta_lr: float
) -> None:
    """Update audit summary with reflex reinforcement marker."""
    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing content or create new
    if Path(audit_path).exists():
        content = Path(audit_path).read_text(encoding="utf-8")
    else:
        content = "# Audit Summary\n\n"
    
    # Build new marker block
    new_block = f"""{AUDIT_MARKER_BEGIN}
🧩 **Reflex Reinforcement**: RRI={rri:+.1f} → {emoji} {classification} (ΔR²={delta_r2:+.3f}, ΔMPI={delta_mpi:+.1f}, ΔLR={delta_lr:+.3f})
{AUDIT_MARKER_END}"""
    
    # Check if marker exists
    if AUDIT_MARKER_BEGIN in content:
        # Replace existing block
        pattern = re.escape(AUDIT_MARKER_BEGIN) + r".*?" + re.escape(AUDIT_MARKER_END)
        content = re.sub(pattern, new_block, content, flags=re.DOTALL)
    else:
        # Append new block
        content = content.rstrip() + "\n\n" + new_block + "\n"
    
    Path(audit_path).write_text(content, encoding="utf-8")


def evaluate_reflex_reinforcement(
    model_history_path: str = "logs/reflex_model_history.json",
    confidence_adaptation_path: str = "reports/confidence_adaptation.json",
    meta_performance_path: str = "reports/reflex_meta_performance.json",
    output_path: str = "reports/reflex_reinforcement.json",
    audit_path: str = "reports/audit_summary.md"
) -> int:
    """
    Evaluate reflex reinforcement index (RRI).
    
    Returns:
        0 on success
    """
    # Load model history
    model_history = load_json(model_history_path, [])
    if not isinstance(model_history, list):
        model_history = []
    
    # Load confidence adaptation
    confidence_adaptation = load_json(confidence_adaptation_path, {})
    
    # Load meta-performance
    meta_performance = load_json(meta_performance_path, {})
    
    # Extract current and previous metrics
    delta_r2 = 0.0
    delta_mpi = 0.0
    delta_lr = 0.0
    
    # Compute ΔR² from model history
    if len(model_history) >= 2:
        # Get last two entries
        current_entry = model_history[-1]
        previous_entry = model_history[-2]
        
        current_r2 = float(current_entry.get("r2_score", current_entry.get("r2", 0.0)))
        previous_r2 = float(previous_entry.get("r2_score", previous_entry.get("r2", 0.0)))
        
        delta_r2 = current_r2 - previous_r2
    
    # Compute ΔMPI from meta-performance
    if isinstance(meta_performance, dict) and "delta_r2" in meta_performance:
        # Meta-performance tracks delta R² which we can use as proxy for MPI change
        # MPI ≈ R² × 100, so ΔMPI ≈ ΔR² × 100
        delta_mpi = float(meta_performance.get("delta_r2", 0.0)) * 100
    
    # Compute ΔLR from confidence adaptation
    if isinstance(confidence_adaptation, dict):
        adjusted_lr = float(confidence_adaptation.get("adjusted_learning_rate", 1.0))
        original_lr = float(confidence_adaptation.get("original_learning_rate", 1.0))
        delta_lr = adjusted_lr - original_lr
    
    # Calculate RRI
    # RRI = 100 × (0.5×ΔR² + 0.3×ΔMPI + 0.2×ΔLR)
    rri = 100.0 * (0.5 * delta_r2 + 0.3 * (delta_mpi / 100.0) + 0.2 * delta_lr)
    
    # Classify reinforcement
    if rri >= 10.0:
        classification = "Reinforcing"
        emoji = "🟢"
        interpretation = "Adaptation improved learning outcomes"
    elif rri <= -10.0:
        classification = "Counterproductive"
        emoji = "🔴"
        interpretation = "Adaptation degraded meta-performance"
    else:
        classification = "Neutral"
        emoji = "🟡"
        interpretation = "Little measurable impact"
    
    # Build result
    result = {
        "status": "ok",
        "rri": round(rri, 3),
        "classification": classification,
        "emoji": emoji,
        "interpretation": interpretation,
        "components": {
            "delta_r2": round(delta_r2, 3),
            "delta_mpi": round(delta_mpi, 3),
            "delta_lr": round(delta_lr, 3)
        },
        "weights": {
            "r2_weight": 0.5,
            "mpi_weight": 0.3,
            "lr_weight": 0.2
        },
        "history_samples": len(model_history),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Save reinforcement result
    save_json(output_path, result)
    
    # Update audit summary
    update_audit_summary(
        audit_path,
        rri,
        classification,
        emoji,
        delta_r2,
        delta_mpi,
        delta_lr
    )
    
    # Output JSON to stdout for CI logging
    print(json.dumps(result, indent=2))
    
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Evaluate reflex reinforcement index (RRI) after confidence-weighted adaptation"
    )
    parser.add_argument(
        "--model-history",
        default="logs/reflex_model_history.json",
        help="Path to reflex model history log"
    )
    parser.add_argument(
        "--confidence-adaptation",
        default="reports/confidence_adaptation.json",
        help="Path to confidence adaptation report"
    )
    parser.add_argument(
        "--meta-performance",
        default="reports/reflex_meta_performance.json",
        help="Path to reflex meta-performance report"
    )
    parser.add_argument(
        "--output",
        default="reports/reflex_reinforcement.json",
        help="Path to output reinforcement report"
    )
    parser.add_argument(
        "--audit-summary",
        default="reports/audit_summary.md",
        help="Path to audit summary markdown"
    )
    
    args = parser.parse_args(argv)
    
    return evaluate_reflex_reinforcement(
        model_history_path=args.model_history,
        confidence_adaptation_path=args.confidence_adaptation,
        meta_performance_path=args.meta_performance,
        output_path=args.output,
        audit_path=args.audit_summary
    )


if __name__ == "__main__":
    sys.exit(main())
