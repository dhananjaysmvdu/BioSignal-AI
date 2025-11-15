#!/usr/bin/env python3
"""
MV-CRS Feedback Engine — Phase XXXVII

Closes the governance loop by converting MV-CRS integration signals into actionable
policy recommendations that feed back into threshold, fusion, and RDGL systems.

Full-circle flow: Governance → MV-CRS → Feedback → Governance

Author: GitHub Copilot (Phase XXXVII)
Created: 2025-11-15
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# =====================================================================
# Path Resolution with MVCRS_BASE_DIR Virtualization
# =====================================================================

def _p(relative_path: str) -> Path:
    """
    Resolve path relative to MVCRS_BASE_DIR (if set) or workspace root.
    Enables test isolation via environment variable override.
    """
    base = os.environ.get("MVCRS_BASE_DIR")
    if base:
        return Path(base) / relative_path
    return Path(__file__).resolve().parent.parent.parent / relative_path


# =====================================================================
# Input Loading
# =====================================================================

def load_integration_state() -> Dict[str, Any]:
    """Load MV-CRS integration orchestrator output."""
    path = _p("state/mvcrs_integration_state.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load integration state: {e}", file=sys.stderr)
        return {}


def load_verifier_state() -> Dict[str, Any]:
    """Load challenge verifier state."""
    path = _p("state/challenge_verifier_state.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load verifier state: {e}", file=sys.stderr)
        return {}


def load_policy_fusion() -> Dict[str, Any]:
    """Load policy fusion state."""
    path = _p("state/policy_fusion_state.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load policy fusion: {e}", file=sys.stderr)
        return {}


def load_rdgl_policy() -> Dict[str, Any]:
    """Load RDGL policy adjustments."""
    path = _p("state/rdgl_policy_adjustments.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load RDGL policy: {e}", file=sys.stderr)
        return {}


def load_threshold_policy() -> Dict[str, Any]:
    """Load autonomous threshold policy."""
    path = _p("state/autonomous_threshold_policy.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load threshold policy: {e}", file=sys.stderr)
        return {}


# =====================================================================
# Feedback Computation Logic
# =====================================================================

def compute_threshold_shift(mvcrs_status: str) -> float:
    """
    Compute recommended threshold adjustment percentage.
    
    Rules:
    - failed → +3% (tightening)
    - warning → +1% (caution)
    - ok → -1% (relaxation, clamped by ATTE)
    """
    if mvcrs_status == "failed":
        return 3.0
    elif mvcrs_status == "warning":
        return 1.0
    elif mvcrs_status == "ok":
        return -1.0
    else:
        return 0.0


def compute_fusion_bias(escalation_open: bool, governance_risk: str, mvcrs_status: str) -> str:
    """
    Recommend fusion bias adjustment.
    
    Priority rules:
    1. escalation_open=true → always "raise"
    2. governance_risk=yellow → "steady"
    3. mvcrs_status=failed → "raise"
    4. mvcrs_status=ok → "lower"
    5. default → "steady"
    """
    if escalation_open:
        return "raise"
    if governance_risk == "yellow":
        return "steady"
    if mvcrs_status == "failed":
        return "raise"
    if mvcrs_status == "ok":
        return "lower"
    return "steady"


def compute_rdgl_signal(mvcrs_status: str) -> str:
    """
    Recommend RDGL reinforcement signal.
    
    Rules:
    - failed → penalize (reduce autonomy)
    - warning → neutral (maintain)
    - ok → reinforce (increase confidence)
    """
    if mvcrs_status == "failed":
        return "penalize"
    elif mvcrs_status == "warning":
        return "neutral"
    elif mvcrs_status == "ok":
        return "reinforce"
    else:
        return "neutral"


def compute_confidence(
    integration_state: Dict[str, Any],
    verifier_state: Dict[str, Any],
    policy_fusion: Dict[str, Any]
) -> float:
    """
    Calculate feedback confidence score (0-1) based on:
    - Integration freshness (last_updated within 24h)
    - Signal consistency between MV-CRS components
    - Data completeness
    
    Returns weighted confidence score.
    """
    confidence = 1.0
    
    # Check integration freshness
    last_updated_str = integration_state.get("last_updated", "")
    if last_updated_str:
        try:
            last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - last_updated).total_seconds() / 3600
            if age_hours > 24:
                confidence *= 0.6  # Stale data penalty
            elif age_hours > 12:
                confidence *= 0.8  # Moderate staleness
        except Exception:
            confidence *= 0.7  # Parse error penalty
    else:
        confidence *= 0.5  # Missing timestamp
    
    # Check signal consistency
    mvcrs_core_ok = integration_state.get("mvcrs_core_ok", False)
    verifier_status = verifier_state.get("status", "")
    
    # Inconsistent signals reduce confidence
    if mvcrs_core_ok and verifier_status == "CHALLENGE_FAILED":
        confidence *= 0.4  # Contradictory signals
    
    # Check data completeness
    required_fields = ["final_decision", "governance_risk_level", "escalation_open"]
    missing = sum(1 for field in required_fields if field not in integration_state)
    if missing > 0:
        confidence *= (1.0 - (missing * 0.15))  # Penalty per missing field
    
    # Clamp to [0, 1]
    return max(0.0, min(1.0, confidence))


def build_feedback_object(
    integration_state: Dict[str, Any],
    verifier_state: Dict[str, Any],
    policy_fusion: Dict[str, Any],
    rdgl_policy: Dict[str, Any],
    threshold_policy: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Synthesize all inputs into feedback impact object.
    
    Returns structured feedback with recommendations for:
    - Threshold adjustments
    - Fusion bias
    - RDGL reinforcement
    - Confidence score
    """
    # Extract core signals
    final_decision = integration_state.get("final_decision", "blocked")
    escalation_open = integration_state.get("escalation_open", False)
    governance_risk = integration_state.get("governance_risk_level", "red")
    mvcrs_core_ok = integration_state.get("mvcrs_core_ok", False)
    
    # Map to mvcrs_status
    if not mvcrs_core_ok:
        mvcrs_status = "failed"
    elif escalation_open:
        mvcrs_status = "warning"
    else:
        mvcrs_status = "ok"
    
    # Compute recommendations
    threshold_shift = compute_threshold_shift(mvcrs_status)
    fusion_bias = compute_fusion_bias(escalation_open, governance_risk, mvcrs_status)
    rdgl_signal = compute_rdgl_signal(mvcrs_status)
    confidence = compute_confidence(integration_state, verifier_state, policy_fusion)
    
    return {
        "mvcrs_status": mvcrs_status,
        "escalation_open": escalation_open,
        "governance_risk": governance_risk,
        "recommended_threshold_shift_pct": threshold_shift,
        "recommended_fusion_bias": fusion_bias,
        "rdgl_signal": rdgl_signal,
        "feedback_confidence": round(confidence, 3),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# =====================================================================
# Output Writing with Atomic Guarantees
# =====================================================================

def write_feedback_state(feedback: Dict[str, Any]) -> bool:
    """
    Atomically write feedback state with 1s/3s/9s retry pattern.
    Returns True on success, False on persistent failure.
    """
    path = _p("state/mvcrs_feedback.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    for delay in [1, 3, 9]:
        try:
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(feedback, f, indent=2)
            tmp.replace(path)
            print(f"✓ Wrote feedback state: {path}")
            return True
        except Exception as e:
            print(f"⚠ Write failed (retry in {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    
    print(f"✗ Persistent write failure: {path}", file=sys.stderr)
    return False


def append_feedback_log(feedback: Dict[str, Any]) -> bool:
    """
    Append feedback to JSONL log with retry pattern.
    Returns True on success, False on persistent failure.
    """
    path = _p("logs/mvcrs_feedback_log.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    for delay in [1, 3, 9]:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(feedback) + "\n")
            print(f"✓ Appended to feedback log: {path}")
            return True
        except Exception as e:
            print(f"⚠ Log append failed (retry in {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    
    print(f"✗ Persistent log append failure: {path}", file=sys.stderr)
    return False


def update_audit_marker(status: str) -> bool:
    """
    Update idempotent audit marker in execution summary.
    Status: UPDATED | FAILED
    """
    summary_path = _p("INSTRUCTION_EXECUTION_SUMMARY.md")
    if not summary_path.exists():
        print(f"⚠ Summary file not found: {summary_path}", file=sys.stderr)
        return False
    
    timestamp = datetime.now(timezone.utc).isoformat()
    marker = f"<!-- MVCRS_FEEDBACK: {status} {timestamp} -->"
    
    for delay in [1, 3, 9]:
        try:
            content = summary_path.read_text(encoding="utf-8")
            
            # Remove old markers
            lines = [line for line in content.split("\n") 
                     if not line.strip().startswith("<!-- MVCRS_FEEDBACK:")]
            
            # Append new marker
            lines.append(marker)
            
            # Atomic write
            tmp = summary_path.with_suffix(".tmp")
            tmp.write_text("\n".join(lines), encoding="utf-8")
            tmp.replace(summary_path)
            
            print(f"✓ Updated audit marker: {status}")
            return True
        except Exception as e:
            print(f"⚠ Marker update failed (retry in {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    
    print(f"✗ Persistent marker update failure", file=sys.stderr)
    return False


def create_fix_branch() -> None:
    """Create fix branch on persistent write failure."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    branch_name = f"fix/mvcrs-feedback-{timestamp}"
    
    try:
        import subprocess
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            print(f"✓ Created fix branch: {branch_name}")
        else:
            print(f"⚠ Failed to create fix branch: {result.stderr}", file=sys.stderr)
    except Exception as e:
        print(f"⚠ Fix branch creation error: {e}", file=sys.stderr)


# =====================================================================
# Main Orchestration
# =====================================================================

def run_feedback_engine() -> int:
    """
    Main feedback engine orchestration.
    
    Returns:
    - 0: Success
    - 1: Partial failure (non-critical)
    - 2: Critical failure (persistent write errors)
    """
    print("=" * 60)
    print("MV-CRS Feedback Engine — Phase XXXVII")
    print("=" * 60)
    
    # Load all inputs
    print("\n[1/4] Loading input states...")
    integration_state = load_integration_state()
    verifier_state = load_verifier_state()
    policy_fusion = load_policy_fusion()
    rdgl_policy = load_rdgl_policy()
    threshold_policy = load_threshold_policy()
    
    if not integration_state:
        print("⚠ No integration state found — feedback cannot be computed", file=sys.stderr)
        return 1
    
    # Compute feedback
    print("\n[2/4] Computing feedback recommendations...")
    feedback = build_feedback_object(
        integration_state,
        verifier_state,
        policy_fusion,
        rdgl_policy,
        threshold_policy
    )
    
    print(f"  Status: {feedback['mvcrs_status']}")
    print(f"  Threshold Shift: {feedback['recommended_threshold_shift_pct']:+.1f}%")
    print(f"  Fusion Bias: {feedback['recommended_fusion_bias']}")
    print(f"  RDGL Signal: {feedback['rdgl_signal']}")
    print(f"  Confidence: {feedback['feedback_confidence']:.3f}")
    
    # Write outputs
    print("\n[3/4] Writing feedback artifacts...")
    state_ok = write_feedback_state(feedback)
    log_ok = append_feedback_log(feedback)
    
    if not (state_ok and log_ok):
        print("\n✗ Critical: Persistent write failures detected", file=sys.stderr)
        create_fix_branch()
        update_audit_marker("FAILED")
        return 2
    
    # Update audit marker
    print("\n[4/4] Updating audit marker...")
    marker_ok = update_audit_marker("UPDATED")
    
    if not marker_ok:
        print("⚠ Audit marker update failed (non-critical)", file=sys.stderr)
        return 1
    
    print("\n" + "=" * 60)
    print("✓ Feedback engine completed successfully")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_feedback_engine())
