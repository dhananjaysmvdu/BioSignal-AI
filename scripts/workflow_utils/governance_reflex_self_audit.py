#!/usr/bin/env python3
"""
Governance Reflex Self-Audit Aggregator

Consolidates all self-assessment metrics (REI, MPI, RRI, Confidence) into a single
timestamped governance self-audit record capturing overall reflex health.

Reflex Health Score = (
    (rei_score / 100) * 0.4 +
    (mpi_score / 100) * 0.3 +
    (confidence_weight) * 0.2 +
    (rri_score / 100) * 0.1
) * 100

Classifications:
  ≥ 80:    🟢 Optimal Reflex Health (system operating efficiently)
  60-79:   🟡 Stable (normal adaptive oscillation)
  < 60:    🔴 Degraded Reflex (requires intervention)

Inputs:
  - reports/reflex_evaluation.json (REI, classification)
  - reports/reflex_meta_performance.json (MPI, status)
  - reports/confidence_adaptation.json (confidence_weight, trust_status)
  - reports/reflex_reinforcement.json (RRI, classification)

Outputs:
  - reports/reflex_self_audit.json
  - reports/audit_summary.md (REFLEX_SELF_AUDIT marker)
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


AUDIT_MARKER_BEGIN = "<!-- REFLEX_SELF_AUDIT:BEGIN -->"
AUDIT_MARKER_END = "<!-- REFLEX_SELF_AUDIT:END -->"


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


def normalize_rei_to_score(rei: float) -> float:
    """
    Normalize REI (typically -10 to +10) to a 0-100 scale.
    REI of 0 = 50, positive REI increases score, negative decreases.
    """
    # Clamp REI to reasonable range
    rei = min(max(rei, -10.0), 10.0)
    # Map [-10, +10] to [0, 100]
    return ((rei + 10.0) / 20.0) * 100.0


def normalize_rri_to_score(rri: float) -> float:
    """
    Normalize RRI (typically -50 to +50) to a 0-100 scale.
    RRI of 0 = 50, positive RRI increases score, negative decreases.
    """
    # Clamp RRI to reasonable range
    rri = min(max(rri, -50.0), 50.0)
    # Map [-50, +50] to [0, 100]
    return ((rri + 50.0) / 100.0) * 100.0


def update_audit_summary(
    audit_path: str,
    health_score: float,
    health_label: str,
    health_emoji: str,
    rei_classification: str,
    mpi_status: str,
    confidence_status: str,
    timestamp: Optional[str] = None,
) -> None:
    """Update audit summary with reflex self-audit marker."""
    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing content or create new
    if Path(audit_path).exists():
        content = Path(audit_path).read_text(encoding="utf-8")
    else:
        content = "# Audit Summary\n\n"
    
    # Normalize timestamp to UTC ISO8601 Z-suffix
    normalized_ts = timestamp
    if normalized_ts:
        try:
            dt = datetime.fromisoformat(normalized_ts.replace("Z", "+00:00"))
            normalized_ts = dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            normalized_ts = None
    if not normalized_ts:
        normalized_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # Build new marker block
    new_block = f"""{AUDIT_MARKER_BEGIN}
Updated: {normalized_ts}
🧠 **Reflex Self-Audit**: Health={health_score:.1f}% → {health_emoji} {health_label} (REI={rei_classification}, MPI={mpi_status}, Confidence={confidence_status})
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


def load_history_for_trend(history_path: str, max_entries: int = 10) -> List[float]:
    """Load historical health scores for trend calculation."""
    history = load_json(history_path, [])
    if not isinstance(history, list):
        return []
    
    # Extract health scores from history
    scores = []
    for entry in history[-max_entries:]:
        if isinstance(entry, dict) and "health_score" in entry:
            scores.append(float(entry["health_score"]))
    
    return scores


def compute_reflex_self_audit(
    reflex_eval_path: str = "reports/reflex_evaluation.json",
    meta_performance_path: str = "reports/reflex_meta_performance.json",
    confidence_adaptation_path: str = "reports/confidence_adaptation.json",
    reinforcement_path: str = "reports/reflex_reinforcement.json",
    output_path: str = "reports/reflex_self_audit.json",
    audit_path: str = "reports/audit_summary.md",
    history_path: str = "logs/reflex_self_audit_history.json"
) -> int:
    """
    Compute comprehensive reflex self-audit and health score.
    
    Returns:
        0 on success
    """
    # Load reflex evaluation (REI)
    reflex_eval = load_json(reflex_eval_path, {})
    rei = float(reflex_eval.get("rei", 0.0))
    rei_classification = reflex_eval.get("classification", "Neutral")
    rei_score = normalize_rei_to_score(rei)
    
    # Load meta-performance (MPI)
    meta_performance = load_json(meta_performance_path, {})
    mpi = float(meta_performance.get("mpi", 50.0))
    mpi_status = meta_performance.get("classification", "Unknown")
    
    # Load confidence adaptation
    confidence_adaptation = load_json(confidence_adaptation_path, {})
    confidence_weight = float(confidence_adaptation.get("confidence_weight", 0.5))
    confidence_status = confidence_adaptation.get("trust_status", "Moderate trust")
    
    # Load reflex reinforcement (RRI)
    reinforcement = load_json(reinforcement_path, {})
    rri = float(reinforcement.get("rri", 0.0))
    rri_classification = reinforcement.get("classification", "Neutral")
    rri_score = normalize_rri_to_score(rri)
    
    # Compute weighted health score
    # reflex_health_score = (rei * 0.4 + mpi * 0.3 + confidence * 0.2 + rri * 0.1)
    health_score = (
        (rei_score / 100.0) * 0.4 +
        (mpi / 100.0) * 0.3 +
        confidence_weight * 0.2 +
        (rri_score / 100.0) * 0.1
    ) * 100.0
    
    # Classify health
    if health_score >= 80.0:
        health_label = "Optimal Reflex Health"
        health_emoji = "🟢"
        health_interpretation = "System operating efficiently"
    elif health_score >= 60.0:
        health_label = "Stable"
        health_emoji = "🟡"
        health_interpretation = "Normal adaptive oscillation"
    else:
        health_label = "Degraded Reflex"
        health_emoji = "🔴"
        health_interpretation = "Requires intervention"
    
    # Load historical scores for trend
    historical_scores = load_history_for_trend(history_path)
    historical_scores.append(health_score)
    
    # Compute rolling mean (last 10)
    rolling_mean = sum(historical_scores[-10:]) / len(historical_scores[-10:]) if historical_scores else health_score
    
    # Determine trend
    if len(historical_scores) >= 2:
        delta = health_score - historical_scores[-2]
        if delta > 5.0:
            trend = "improving"
            trend_emoji = "📈"
        elif delta < -5.0:
            trend = "declining"
            trend_emoji = "📉"
        else:
            trend = "stable"
            trend_emoji = "➡️"
    else:
        trend = "initial"
        trend_emoji = "🆕"
    
    # Build result
    result = {
        "status": "ok",
        "health_score": round(health_score, 3),
        "classification": health_label,
        "emoji": health_emoji,
        "interpretation": health_interpretation,
        "components": {
            "rei": {
                "value": round(rei, 3),
                "normalized_score": round(rei_score, 3),
                "classification": rei_classification,
                "weight": 0.4
            },
            "mpi": {
                "value": round(mpi, 3),
                "classification": mpi_status,
                "weight": 0.3
            },
            "confidence": {
                "value": round(confidence_weight, 3),
                "status": confidence_status,
                "weight": 0.2
            },
            "rri": {
                "value": round(rri, 3),
                "normalized_score": round(rri_score, 3),
                "classification": rri_classification,
                "weight": 0.1
            }
        },
        "trend": {
            "direction": trend,
            "emoji": trend_emoji,
            "rolling_mean_10": round(rolling_mean, 3),
            "samples": len(historical_scores)
        },
    "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    }
    
    # Save self-audit result
    save_json(output_path, result)
    
    # Update history
    history_entry = {
        "health_score": round(health_score, 3),
        "classification": health_label,
        "timestamp": result["timestamp"]
    }
    history = load_json(history_path, [])
    if not isinstance(history, list):
        history = []
    history.append(history_entry)
    save_json(history_path, history)
    
    # Update audit summary
    update_audit_summary(
        audit_path,
        health_score,
        health_label,
        health_emoji,
        rei_classification,
        mpi_status,
        confidence_status,
        timestamp=result["timestamp"],
    )
    
    # Output JSON to stdout for CI logging
    print(json.dumps(result, indent=2))
    
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compute comprehensive reflex self-audit and health classification"
    )
    parser.add_argument(
        "--reflex-eval",
        default="reports/reflex_evaluation.json",
        help="Path to reflex evaluation report"
    )
    parser.add_argument(
        "--meta-performance",
        default="reports/reflex_meta_performance.json",
        help="Path to meta-performance report"
    )
    parser.add_argument(
        "--confidence-adaptation",
        default="reports/confidence_adaptation.json",
        help="Path to confidence adaptation report"
    )
    parser.add_argument(
        "--reinforcement",
        default="reports/reflex_reinforcement.json",
        help="Path to reflex reinforcement report"
    )
    parser.add_argument(
        "--output",
        default="reports/reflex_self_audit.json",
        help="Path to output self-audit report"
    )
    parser.add_argument(
        "--audit-summary",
        default="reports/audit_summary.md",
        help="Path to audit summary markdown"
    )
    parser.add_argument(
        "--history",
        default="logs/reflex_self_audit_history.json",
        help="Path to historical health scores log"
    )
    
    args = parser.parse_args(argv)
    
    return compute_reflex_self_audit(
        reflex_eval_path=args.reflex_eval,
        meta_performance_path=args.meta_performance,
        confidence_adaptation_path=args.confidence_adaptation,
        reinforcement_path=args.reinforcement,
        output_path=args.output,
        audit_path=args.audit_summary,
        history_path=args.history
    )


if __name__ == "__main__":
    sys.exit(main())
