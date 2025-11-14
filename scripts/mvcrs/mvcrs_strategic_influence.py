#!/usr/bin/env python3
"""
MV-CRS Strategic Influence Engine — Phase XXXVIII

Governance meta-layer that shapes the strategic trajectory of multiple subsystems:
- RDGL learning rate
- ATTE shift ceilings
- Policy Fusion sensitivity bands
- Trust Guard scoring weights
- Adaptive Response aggressiveness

Creates strategic influence based on MV-CRS health signals.

Author: GitHub Copilot (Phase XXXVIII)
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

def load_feedback_state() -> Dict[str, Any]:
    """Load MV-CRS feedback recommendations."""
    path = _p("state/mvcrs_feedback.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load feedback state: {e}", file=sys.stderr)
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
    """Load autonomous threshold policy (ATTE)."""
    path = _p("state/autonomous_threshold_policy.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load threshold policy: {e}", file=sys.stderr)
        return {}


def load_trust_lock_state() -> Dict[str, Any]:
    """Load trust lock state."""
    path = _p("state/trust_lock_state.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load trust lock state: {e}", file=sys.stderr)
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


def load_learning_history() -> list:
    """Load learning global history (optional)."""
    path = _p("state/learning_global_history.jsonl")
    if not path.exists():
        return []
    try:
        history = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    history.append(json.loads(line))
        return history
    except Exception as e:
        print(f"⚠ Failed to load learning history: {e}", file=sys.stderr)
        return []


# =====================================================================
# Strategic Influence Computation
# =====================================================================

def determine_mvcrs_health(feedback: Dict[str, Any]) -> str:
    """
    Determine MV-CRS health status from feedback.
    
    Returns: "ok" | "warning" | "failed"
    """
    mvcrs_status = feedback.get("mvcrs_status", "failed")
    
    # Map feedback status to health
    if mvcrs_status == "ok":
        return "ok"
    elif mvcrs_status == "warning":
        return "warning"
    else:  # failed or unknown
        return "failed"


def compute_strategic_profile(mvcrs_health: str, trust_locked: bool, fusion_risk: str) -> str:
    """
    Compute strategic profile based on MV-CRS health and governance context.
    
    Priority rules:
    1. failed OR (trust_locked AND fusion_risk=RED) → "cautious"
    2. warning OR fusion_risk=YELLOW → "stable"
    3. ok AND fusion_risk=GREEN → "aggressive"
    
    Returns: "stable" | "cautious" | "aggressive"
    """
    if mvcrs_health == "failed":
        return "cautious"
    
    if trust_locked and fusion_risk == "RED":
        return "cautious"
    
    if mvcrs_health == "warning" or fusion_risk == "YELLOW":
        return "stable"
    
    if mvcrs_health == "ok" and fusion_risk == "GREEN":
        return "aggressive"
    
    # Default to stable for ambiguous cases
    return "stable"


def compute_rdgl_learning_rate_multiplier(strategic_profile: str) -> float:
    """
    Compute RDGL learning rate multiplier.
    
    - cautious: 0.6 (slow learning)
    - stable: 0.9 (conservative)
    - aggressive: 1.1 (accelerated learning)
    
    Clamped to [0.5, 1.5]
    """
    multipliers = {
        "cautious": 0.6,
        "stable": 0.9,
        "aggressive": 1.1
    }
    value = multipliers.get(strategic_profile, 0.9)
    return max(0.5, min(1.5, value))


def compute_atte_shift_ceiling_pct(strategic_profile: str, base_ceiling: float = 3.0) -> float:
    """
    Compute ATTE shift ceiling percentage.
    
    Base ceiling is typically 3% per 24h.
    
    - cautious: -40% (1.8%)
    - stable: -15% (2.55%)
    - aggressive: +20% (3.6%)
    
    Clamped to [1.0, 5.0]
    """
    adjustments = {
        "cautious": -0.40,
        "stable": -0.15,
        "aggressive": 0.20
    }
    adjustment = adjustments.get(strategic_profile, 0.0)
    value = base_ceiling * (1 + adjustment)
    return max(1.0, min(5.0, value))


def compute_fusion_sensitivity_bias(strategic_profile: str) -> str:
    """
    Compute fusion sensitivity bias.
    
    - cautious: "tighten" (more conservative fusion)
    - stable: "neutral" (maintain current)
    - aggressive: "relax" (more permissive fusion)
    
    Returns: "relax" | "neutral" | "tighten"
    """
    biases = {
        "cautious": "tighten",
        "stable": "neutral",
        "aggressive": "relax"
    }
    return biases.get(strategic_profile, "neutral")


def compute_trust_guard_weight_delta(strategic_profile: str) -> float:
    """
    Compute trust guard scoring weight adjustment.
    
    - cautious: +0.05 (increase trust requirements)
    - stable: +0.02 (slight increase)
    - aggressive: -0.03 (relax trust requirements)
    
    Clamped to [-0.10, +0.10]
    """
    deltas = {
        "cautious": 0.05,
        "stable": 0.02,
        "aggressive": -0.03
    }
    value = deltas.get(strategic_profile, 0.0)
    return max(-0.10, min(0.10, value))


def compute_adaptive_response_aggressiveness(strategic_profile: str, mvcrs_health: str) -> str:
    """
    Compute adaptive response aggressiveness level.
    
    - cautious OR failed: "high" (aggressive intervention)
    - stable OR warning: "medium" (balanced response)
    - aggressive AND ok: "low" (minimal intervention)
    
    Returns: "low" | "medium" | "high"
    """
    if strategic_profile == "cautious" or mvcrs_health == "failed":
        return "high"
    elif strategic_profile == "stable" or mvcrs_health == "warning":
        return "medium"
    elif strategic_profile == "aggressive" and mvcrs_health == "ok":
        return "low"
    else:
        return "medium"


def compute_confidence(
    feedback: Dict[str, Any],
    rdgl_policy: Dict[str, Any],
    threshold_policy: Dict[str, Any],
    trust_lock: Dict[str, Any],
    fusion: Dict[str, Any]
) -> float:
    """
    Compute confidence score for strategic influence.
    
    Factors:
    - Feedback freshness and confidence
    - Availability of governance states
    - Consistency of signals
    
    Returns: 0.0-1.0
    """
    confidence = 1.0
    
    # Check feedback quality
    feedback_confidence = feedback.get("feedback_confidence", 0.0)
    confidence *= feedback_confidence
    
    # Check data availability (each missing state reduces confidence)
    required_states = [rdgl_policy, threshold_policy, trust_lock, fusion]
    missing_count = sum(1 for state in required_states if not state)
    if missing_count > 0:
        confidence *= (1.0 - (missing_count * 0.15))
    
    # Check feedback freshness
    feedback_timestamp = feedback.get("timestamp", "")
    if feedback_timestamp:
        try:
            feedback_time = datetime.fromisoformat(feedback_timestamp.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - feedback_time).total_seconds() / 3600
            if age_hours > 24:
                confidence *= 0.7  # Stale feedback
            elif age_hours > 12:
                confidence *= 0.85
        except Exception:
            confidence *= 0.8  # Parse error
    
    # Clamp to [0, 1]
    return max(0.0, min(1.0, confidence))


def build_strategic_influence_block(
    feedback: Dict[str, Any],
    rdgl_policy: Dict[str, Any],
    threshold_policy: Dict[str, Any],
    trust_lock: Dict[str, Any],
    fusion: Dict[str, Any],
    learning_history: list
) -> Dict[str, Any]:
    """
    Build the Strategic Influence Block (SIB).
    
    Synthesizes all inputs into strategic directives for governance subsystems.
    """
    # Determine core health status
    mvcrs_health = determine_mvcrs_health(feedback)
    
    # Extract governance context
    trust_locked = trust_lock.get("trust_locked", False)
    fusion_risk = fusion.get("fusion_state", "YELLOW")
    
    # Compute strategic profile
    strategic_profile = compute_strategic_profile(mvcrs_health, trust_locked, fusion_risk)
    
    # Compute all influence parameters
    rdgl_multiplier = compute_rdgl_learning_rate_multiplier(strategic_profile)
    atte_ceiling = compute_atte_shift_ceiling_pct(strategic_profile)
    fusion_bias = compute_fusion_sensitivity_bias(strategic_profile)
    trust_delta = compute_trust_guard_weight_delta(strategic_profile)
    aggressiveness = compute_adaptive_response_aggressiveness(strategic_profile, mvcrs_health)
    
    # Compute confidence
    confidence = compute_confidence(feedback, rdgl_policy, threshold_policy, trust_lock, fusion)
    
    return {
        "mvcrs_health": mvcrs_health,
        "strategic_profile": strategic_profile,
        "rdgl_learning_rate_multiplier": round(rdgl_multiplier, 3),
        "atte_shift_ceiling_pct": round(atte_ceiling, 2),
        "fusion_sensitivity_bias": fusion_bias,
        "trust_guard_weight_delta": round(trust_delta, 3),
        "adaptive_response_aggressiveness": aggressiveness,
        "confidence": round(confidence, 3),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# =====================================================================
# Output Writing with Atomic Guarantees
# =====================================================================

def write_strategic_influence_state(sib: Dict[str, Any]) -> bool:
    """
    Atomically write strategic influence state with 1s/3s/9s retry pattern.
    Returns True on success, False on persistent failure.
    """
    path = _p("state/mvcrs_strategic_influence.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    for delay in [1, 3, 9]:
        try:
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(sib, f, indent=2)
            tmp.replace(path)
            print(f"✓ Wrote strategic influence state: {path}")
            return True
        except Exception as e:
            print(f"⚠ Write failed (retry in {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    
    print(f"✗ Persistent write failure: {path}", file=sys.stderr)
    return False


def append_strategic_influence_log(sib: Dict[str, Any]) -> bool:
    """
    Append strategic influence to JSONL log with retry pattern.
    Returns True on success, False on persistent failure.
    """
    path = _p("logs/mvcrs_strategic_influence_log.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    for delay in [1, 3, 9]:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(sib) + "\n")
            print(f"✓ Appended to strategic influence log: {path}")
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
    marker = f"<!-- MVCRS_STRATEGIC_INFLUENCE: {status} {timestamp} -->"
    
    for delay in [1, 3, 9]:
        try:
            content = summary_path.read_text(encoding="utf-8")
            
            # Remove old markers
            lines = [line for line in content.split("\n") 
                     if not line.strip().startswith("<!-- MVCRS_STRATEGIC_INFLUENCE:")]
            
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
    branch_name = f"fix/mvcrs-strategic-influence-{timestamp}"
    
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

def run_strategic_influence_engine() -> int:
    """
    Main strategic influence engine orchestration.
    
    Returns:
    - 0: Success
    - 1: Partial failure (non-critical)
    - 2: Critical failure (persistent write errors)
    """
    print("=" * 60)
    print("MV-CRS Strategic Influence Engine — Phase XXXVIII")
    print("=" * 60)
    
    # Load all inputs
    print("\n[1/4] Loading input states...")
    feedback = load_feedback_state()
    rdgl_policy = load_rdgl_policy()
    threshold_policy = load_threshold_policy()
    trust_lock = load_trust_lock_state()
    fusion = load_policy_fusion()
    learning_history = load_learning_history()
    
    if not feedback:
        print("⚠ No feedback state found — strategic influence cannot be computed", file=sys.stderr)
        return 1
    
    # Build strategic influence block
    print("\n[2/4] Computing strategic influence...")
    sib = build_strategic_influence_block(
        feedback,
        rdgl_policy,
        threshold_policy,
        trust_lock,
        fusion,
        learning_history
    )
    
    print(f"  MV-CRS Health: {sib['mvcrs_health']}")
    print(f"  Strategic Profile: {sib['strategic_profile']}")
    print(f"  RDGL Learning Rate: {sib['rdgl_learning_rate_multiplier']:.3f}×")
    print(f"  ATTE Shift Ceiling: {sib['atte_shift_ceiling_pct']:.2f}%")
    print(f"  Fusion Sensitivity: {sib['fusion_sensitivity_bias']}")
    print(f"  Trust Guard Δ: {sib['trust_guard_weight_delta']:+.3f}")
    print(f"  Response Aggressiveness: {sib['adaptive_response_aggressiveness']}")
    print(f"  Confidence: {sib['confidence']:.3f}")
    
    # Write outputs
    print("\n[3/4] Writing strategic influence artifacts...")
    state_ok = write_strategic_influence_state(sib)
    log_ok = append_strategic_influence_log(sib)
    
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
    print("✓ Strategic influence engine completed successfully")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_strategic_influence_engine())
