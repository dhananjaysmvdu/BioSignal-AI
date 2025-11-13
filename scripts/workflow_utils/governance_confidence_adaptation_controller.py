#!/usr/bin/env python3
"""
Governance Confidence-Weighted Adaptation Controller

Automatically scales learning-rate updates based on forecast confidence.
When the system is uncertain about predictions, it tempers adaptation speed.
When highly confident, it allows full responsiveness.

Inputs:
  - reports/forecast_confidence.json (confidence_weight 0.0-1.0)
  - reports/governance_policy.json (current learning policy)

Outputs:
  - reports/confidence_adaptation.json
  - reports/governance_policy.json (updated with adjusted rate)
  - reports/audit_summary.md (CONFIDENCE_ADAPTATION marker)
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


AUDIT_MARKER_BEGIN = "<!-- CONFIDENCE_ADAPTATION:BEGIN -->"
AUDIT_MARKER_END = "<!-- CONFIDENCE_ADAPTATION:END -->"


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
    trust_status: str,
    adjusted_rate: float,
    confidence: float
) -> None:
    """Update audit summary with confidence adaptation marker."""
    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing content or create new
    if Path(audit_path).exists():
        content = Path(audit_path).read_text(encoding="utf-8")
    else:
        content = "# Audit Summary\n\n"
    
    # Build new marker block
    new_block = f"""{AUDIT_MARKER_BEGIN}
🧭 **Confidence-Weighted Adaptation**: trust={trust_status}, lr→{adjusted_rate:.3f} (confidence={confidence:.3f})
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


def apply_confidence_adaptation(
    confidence_path: str = "reports/forecast_confidence.json",
    policy_path: str = "reports/governance_policy.json",
    output_path: str = "reports/confidence_adaptation.json",
    audit_path: str = "reports/audit_summary.md"
) -> int:
    """
    Apply confidence-weighted adaptation to learning parameters.
    
    Returns:
        0 on success
    """
    # Load forecast confidence (default: full confidence)
    forecast_confidence = load_json(confidence_path, {})
    confidence = float(forecast_confidence.get("confidence_weight", 1.0))
    confidence = min(max(confidence, 0.0), 1.0)  # Clamp to [0, 1]
    
    # Load current governance policy (default: baseline)
    policy = load_json(policy_path, {})
    learning_rate = float(policy.get("learning_rate_factor", 1.0))
    
    # Scale learning rate by confidence
    adjusted_rate = learning_rate * confidence
    adjusted_rate = min(max(adjusted_rate, 0.2), 1.5)  # Clamp to [0.2, 1.5]
    
    # Determine trust label
    if confidence >= 0.8:
        trust_status = "High trust"
    elif confidence >= 0.5:
        trust_status = "Moderate trust"
    else:
        trust_status = "Low trust"
    
    # Build result
    result = {
        "status": "ok",
        "confidence_weight": round(confidence, 3),
        "original_learning_rate": round(learning_rate, 3),
        "adjusted_learning_rate": round(adjusted_rate, 3),
        "trust_status": trust_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Save confidence adaptation result
    save_json(output_path, result)
    
    # Update governance policy with adjusted rate
    policy["learning_rate_factor"] = round(adjusted_rate, 3)
    save_json(policy_path, policy)
    
    # Update audit summary
    update_audit_summary(audit_path, trust_status, adjusted_rate, confidence)
    
    # Output JSON to stdout for CI logging
    print(json.dumps(result, indent=2))
    
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Apply confidence-weighted adaptation to learning parameters"
    )
    parser.add_argument(
        "--confidence",
        default="reports/forecast_confidence.json",
        help="Path to forecast confidence report"
    )
    parser.add_argument(
        "--policy",
        default="reports/governance_policy.json",
        help="Path to governance policy (will be updated)"
    )
    parser.add_argument(
        "--output",
        default="reports/confidence_adaptation.json",
        help="Path to output adaptation report"
    )
    parser.add_argument(
        "--audit-summary",
        default="reports/audit_summary.md",
        help="Path to audit summary markdown"
    )
    
    args = parser.parse_args(argv)
    
    return apply_confidence_adaptation(
        confidence_path=args.confidence,
        policy_path=args.policy,
        output_path=args.output,
        audit_path=args.audit_summary
    )


if __name__ == "__main__":
    sys.exit(main())
