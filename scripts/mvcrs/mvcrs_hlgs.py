#!/usr/bin/env python3
"""
MV-CRS Unified Long-Horizon Governance Synthesizer (HLGS) — Phase XXXIX

Extends governance from daily reactive responses to 30-45 day strategic prediction
and autonomous planning. Combines MV-CRS signals, RDGL patterns, ATTE drifts,
fusion cycles, trust events, forensic trends, and strategic influence into a
comprehensive long-horizon governance plan.

This is the "planning cortex" that enables proactive governance evolution.

Author: GitHub Copilot (Phase XXXIX)
Created: 2025-11-15
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
# Input Loading (Mandatory)
# =====================================================================

def load_feedback_state() -> Dict[str, Any]:
    """Load MV-CRS feedback recommendations (mandatory)."""
    path = _p("state/mvcrs_feedback.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load feedback state: {e}", file=sys.stderr)
        return {}


def load_strategic_influence() -> Dict[str, Any]:
    """Load MV-CRS strategic influence (mandatory)."""
    path = _p("state/mvcrs_strategic_influence.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load strategic influence: {e}", file=sys.stderr)
        return {}


def load_policy_fusion() -> Dict[str, Any]:
    """Load policy fusion state (mandatory)."""
    path = _p("state/policy_fusion_state.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load policy fusion: {e}", file=sys.stderr)
        return {}


def load_threshold_policy() -> Dict[str, Any]:
    """Load autonomous threshold policy (mandatory)."""
    path = _p("state/autonomous_threshold_policy.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load threshold policy: {e}", file=sys.stderr)
        return {}


def load_rdgl_policy() -> Dict[str, Any]:
    """Load RDGL policy adjustments (mandatory)."""
    path = _p("state/rdgl_policy_adjustments.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load RDGL policy: {e}", file=sys.stderr)
        return {}


# =====================================================================
# Input Loading (Optional)
# =====================================================================

def load_forensic_forecast() -> Dict[str, Any]:
    """Load forensic forecast (optional)."""
    path = _p("state/forensic_forecast.json")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Failed to load forensic forecast: {e}", file=sys.stderr)
        return {}


def load_history_log(log_name: str, max_lines: int = 100) -> list:
    """Load history JSONL file (optional)."""
    path = _p(f"state/{log_name}")
    if not path.exists():
        return []
    try:
        history = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    history.append(json.loads(line))
                if len(history) >= max_lines:
                    break
        return history
    except Exception as e:
        print(f"⚠ Failed to load {log_name}: {e}", file=sys.stderr)
        return []


# =====================================================================
# Trend Analysis
# =====================================================================

def analyze_mvcrs_health_trend(feedback: Dict[str, Any], strategic: Dict[str, Any]) -> str:
    """
    Analyze MV-CRS health trend over time.
    
    Returns: "improving" | "stable" | "declining"
    """
    mvcrs_health = strategic.get("mvcrs_health", "unknown")
    strategic_profile = strategic.get("strategic_profile", "stable")
    
    # Map to trend
    if mvcrs_health == "ok" and strategic_profile == "aggressive":
        return "improving"
    elif mvcrs_health == "failed" or strategic_profile == "cautious":
        return "declining"
    else:
        return "stable"


def analyze_rdgl_trajectory(rdgl: Dict[str, Any]) -> str:
    """
    Analyze RDGL policy trajectory.
    
    Returns: "upward" | "sideways" | "downward"
    """
    # Check RDGL mode and policy score
    mode = rdgl.get("mode", "disabled")
    policy_score = rdgl.get("policy_score", 0.5)
    
    if mode == "disabled":
        return "sideways"
    
    # Trajectory based on policy score
    if policy_score > 0.7:
        return "upward"
    elif policy_score < 0.4:
        return "downward"
    else:
        return "sideways"


def analyze_atte_pressure(threshold_policy: Dict[str, Any], strategic: Dict[str, Any]) -> str:
    """
    Analyze ATTE threshold adjustment pressure.
    
    Returns: "low" | "medium" | "high"
    """
    shift_ceiling = strategic.get("atte_shift_ceiling_pct", 3.0)
    profile = strategic.get("strategic_profile", "stable")
    
    # Pressure based on shift ceiling and profile
    # Aggressive profile with high ceiling = low pressure
    if shift_ceiling >= 3.0 and profile == "aggressive":
        return "low"  # High ceiling + aggressive = low pressure (relaxed)
    elif shift_ceiling >= 3.5:
        return "low"  # Very high ceiling = low pressure
    elif shift_ceiling <= 2.0:
        return "high"  # Low ceiling = high pressure (tight)
    else:
        return "medium"


def predict_fusion_cycle(fusion: Dict[str, Any], strategic: Dict[str, Any]) -> str:
    """
    Predict policy fusion cycle direction.
    
    Returns: "relax" | "steady" | "tighten"
    """
    fusion_state = fusion.get("fusion_state", "YELLOW")
    fusion_bias = strategic.get("fusion_sensitivity_bias", "neutral")
    
    # Combine current state with strategic bias
    if fusion_bias == "relax" or fusion_state == "GREEN":
        return "relax"
    elif fusion_bias == "tighten" or fusion_state == "RED":
        return "tighten"
    else:
        return "steady"


# =====================================================================
# Risk Projection
# =====================================================================

def project_forensic_risk(forensic: Dict[str, Any]) -> float:
    """
    Project forensic risk over 45-day horizon.
    
    Returns: 0.0-1.0 risk score
    """
    if not forensic:
        return 0.3  # Default moderate risk when no data
    
    # Extract forensic metrics
    anomaly_count = forensic.get("anomaly_count", 0)
    drift_probability = forensic.get("drift_probability", 0.0)
    
    # Compute projected risk
    risk = (anomaly_count / 100.0) * 0.5 + drift_probability * 0.5
    return max(0.0, min(1.0, risk))


def predict_policy_instability(
    feedback: Dict[str, Any],
    strategic: Dict[str, Any],
    fusion: Dict[str, Any],
    rdgl: Dict[str, Any]
) -> float:
    """
    Predict policy instability over 45-day horizon.
    
    Returns: 0.0-1.0 instability score
    """
    instability = 0.0
    
    # MV-CRS health contribution
    mvcrs_health = strategic.get("mvcrs_health", "ok")
    if mvcrs_health == "failed":
        instability += 0.4
    elif mvcrs_health == "warning":
        instability += 0.2
    
    # Fusion state contribution
    fusion_state = fusion.get("fusion_state", "GREEN")
    if fusion_state == "RED":
        instability += 0.3
    elif fusion_state == "YELLOW":
        instability += 0.15
    
    # Strategic confidence contribution
    confidence = strategic.get("confidence", 1.0)
    instability += (1.0 - confidence) * 0.3
    
    return max(0.0, min(1.0, instability))


def estimate_trust_events(strategic: Dict[str, Any], policy_history: list) -> int:
    """
    Estimate expected trust lock/unlock events over 45-day horizon.
    
    Returns: Number of expected trust events
    """
    trust_delta = strategic.get("trust_guard_weight_delta", 0.0)
    
    # Estimate based on trust delta magnitude
    if abs(trust_delta) > 0.04:
        return 3  # High trust volatility
    elif abs(trust_delta) > 0.02:
        return 2  # Moderate trust volatility
    else:
        return 1  # Low trust volatility


# =====================================================================
# Instability Cluster Detection
# =====================================================================

def detect_instability_clusters(
    mvcrs_trend: str,
    forensic_risk: float,
    policy_instability: float,
    fusion_cycle: str,
    atte_pressure: str
) -> int:
    """
    Detect instability clusters (3+ warnings).
    
    Returns: Number of warning signals
    """
    warnings = 0
    
    if mvcrs_trend == "declining":
        warnings += 1
    
    if forensic_risk > 0.6:
        warnings += 1
    
    if policy_instability > 0.5:
        warnings += 1
    
    if fusion_cycle == "tighten":
        warnings += 1
    
    if atte_pressure == "high":
        warnings += 1
    
    return warnings


# =====================================================================
# Status Determination & Action Recommendation
# =====================================================================

def determine_overall_status(instability_clusters: int, policy_instability: float) -> str:
    """
    Determine overall governance status.
    
    Returns: "stable" | "volatile" | "critical"
    """
    if instability_clusters >= 3 or policy_instability > 0.7:
        return "critical"
    elif instability_clusters >= 2 or policy_instability > 0.4:
        return "volatile"
    else:
        return "stable"


def recommend_governance_actions(
    status: str,
    mvcrs_trend: str,
    forensic_risk: float,
    policy_instability: float,
    atte_pressure: str,
    fusion_cycle: str
) -> List[str]:
    """
    Recommend governance actions based on status and signals.
    
    Returns: List of recommended action strings
    """
    actions = []
    
    if status == "critical":
        # 2-3 preventive interventions
        actions.append("increase_threshold_headroom")
        actions.append("prepare_self_healing_window")
        
        if forensic_risk > 0.7:
            actions.append("raise_fusion_sensitivity")
        
        if policy_instability > 0.7:
            actions.append("hold_current_policy")
    
    elif status == "volatile":
        # 1-2 policy stabilizers
        actions.append("hold_current_policy")
        
        if atte_pressure == "high":
            actions.append("increase_threshold_headroom")
        elif fusion_cycle == "tighten":
            actions.append("raise_fusion_sensitivity")
    
    else:  # stable
        # Minimal, advisory-only
        if mvcrs_trend == "improving":
            actions.append("lower_adaptive_response_frequency")
        else:
            actions.append("monitor_governance_metrics")
    
    return actions


# =====================================================================
# Confidence Scoring
# =====================================================================

def compute_hlgs_confidence(
    feedback: Dict[str, Any],
    strategic: Dict[str, Any],
    has_forensic: bool,
    has_policy_history: bool,
    has_learning_history: bool
) -> float:
    """
    Compute HLGS confidence score.
    
    Factors:
    - Feedback freshness
    - Strategic influence quality
    - Optional data completeness
    
    Returns: 0.0-1.0
    """
    confidence = 1.0
    
    # Strategic influence confidence
    strategic_confidence = strategic.get("confidence", 0.5)
    confidence *= strategic_confidence
    
    # Feedback freshness
    feedback_timestamp = feedback.get("timestamp", "")
    if feedback_timestamp:
        try:
            feedback_time = datetime.fromisoformat(feedback_timestamp.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - feedback_time).total_seconds() / 3600
            if age_hours > 48:
                confidence *= 0.6  # Very stale
            elif age_hours > 24:
                confidence *= 0.8  # Stale
        except Exception:
            confidence *= 0.7  # Parse error
    
    # Optional data bonus (small boost for completeness)
    optional_count = sum([has_forensic, has_policy_history, has_learning_history])
    confidence *= (1.0 + optional_count * 0.05)
    
    return max(0.0, min(1.0, confidence))


# =====================================================================
# Long-Horizon Plan Synthesis
# =====================================================================

def build_long_horizon_plan(
    feedback: Dict[str, Any],
    strategic: Dict[str, Any],
    fusion: Dict[str, Any],
    threshold_policy: Dict[str, Any],
    rdgl: Dict[str, Any],
    forensic: Dict[str, Any],
    policy_history: list,
    learning_history: list
) -> Dict[str, Any]:
    """
    Synthesize comprehensive 45-day governance plan.
    
    Combines trend analysis, risk projection, and action recommendations.
    """
    # Trend analysis
    mvcrs_trend = analyze_mvcrs_health_trend(feedback, strategic)
    rdgl_trajectory = analyze_rdgl_trajectory(rdgl)
    atte_pressure = analyze_atte_pressure(threshold_policy, strategic)
    fusion_cycle = predict_fusion_cycle(fusion, strategic)
    
    # Risk projection
    forensic_risk = project_forensic_risk(forensic)
    policy_instability = predict_policy_instability(feedback, strategic, fusion, rdgl)
    trust_events = estimate_trust_events(strategic, policy_history)
    
    # Instability detection
    instability_clusters = detect_instability_clusters(
        mvcrs_trend, forensic_risk, policy_instability, fusion_cycle, atte_pressure
    )
    
    # Status determination
    status = determine_overall_status(instability_clusters, policy_instability)
    
    # Action recommendations
    actions = recommend_governance_actions(
        status, mvcrs_trend, forensic_risk, policy_instability, atte_pressure, fusion_cycle
    )
    
    # Confidence scoring
    confidence = compute_hlgs_confidence(
        feedback,
        strategic,
        has_forensic=bool(forensic),
        has_policy_history=bool(policy_history),
        has_learning_history=bool(learning_history)
    )
    
    return {
        "status": status,
        "horizon_days": 45,
        "mvcrs_health_trend": mvcrs_trend,
        "forensic_risk_projection": round(forensic_risk, 3),
        "predicted_policy_instability": round(policy_instability, 3),
        "expected_trust_events": trust_events,
        "rdgl_trajectory": rdgl_trajectory,
        "atte_pressure": atte_pressure,
        "fusion_cycle_prediction": fusion_cycle,
        "recommended_governance_actions": actions,
        "confidence": round(confidence, 3),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# =====================================================================
# Output Writing with Atomic Guarantees
# =====================================================================

def write_long_horizon_plan(plan: Dict[str, Any]) -> bool:
    """
    Atomically write long-horizon plan with 1s/3s/9s retry pattern.
    Returns True on success, False on persistent failure.
    """
    path = _p("state/mvcrs_long_horizon_plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    for delay in [1, 3, 9]:
        try:
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2)
            tmp.replace(path)
            print(f"✓ Wrote long-horizon plan: {path}")
            return True
        except Exception as e:
            print(f"⚠ Write failed (retry in {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    
    print(f"✗ Persistent write failure: {path}", file=sys.stderr)
    return False


def append_hlgs_log(plan: Dict[str, Any]) -> bool:
    """
    Append plan to JSONL log with retry pattern.
    Returns True on success, False on persistent failure.
    """
    path = _p("logs/mvcrs_hlgs_log.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    for delay in [1, 3, 9]:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(plan) + "\n")
            print(f"✓ Appended to HLGS log: {path}")
            return True
        except Exception as e:
            print(f"⚠ Log append failed (retry in {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    
    print(f"✗ Persistent log append failure: {path}", file=sys.stderr)
    return False


def update_audit_marker(status: str) -> bool:
    """
    Update idempotent audit marker in execution summary.
    Status: UPDATED | CRITICAL
    """
    summary_path = _p("INSTRUCTION_EXECUTION_SUMMARY.md")
    if not summary_path.exists():
        print(f"⚠ Summary file not found: {summary_path}", file=sys.stderr)
        return False
    
    timestamp = datetime.now(timezone.utc).isoformat()
    marker = f"<!-- MVCRS_HLGS: {status} {timestamp} -->"
    
    for delay in [1, 3, 9]:
        try:
            content = summary_path.read_text(encoding="utf-8")
            
            # Remove old markers
            lines = [line for line in content.split("\n") 
                     if not line.strip().startswith("<!-- MVCRS_HLGS:")]
            
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
    branch_name = f"fix/mvcrs-hlgs-{timestamp}"
    
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

def run_hlgs_engine() -> int:
    """
    Main long-horizon governance synthesizer orchestration.
    
    Returns:
    - 0: Success
    - 1: Partial failure (non-critical)
    - 2: Critical failure (persistent write errors)
    """
    print("=" * 60)
    print("MV-CRS Long-Horizon Governance Synthesizer — Phase XXXIX")
    print("=" * 60)
    
    # Load mandatory inputs
    print("\n[1/4] Loading mandatory inputs...")
    feedback = load_feedback_state()
    strategic = load_strategic_influence()
    fusion = load_policy_fusion()
    threshold_policy = load_threshold_policy()
    rdgl = load_rdgl_policy()
    
    if not (feedback and strategic):
        print("⚠ Missing mandatory inputs (feedback or strategic) — cannot compute plan", file=sys.stderr)
        return 1
    
    # Load optional inputs
    print("\n[2/4] Loading optional inputs...")
    forensic = load_forensic_forecast()
    policy_history = load_history_log("policy_history.jsonl", max_lines=50)
    learning_history = load_history_log("learning_global_history.jsonl", max_lines=50)
    
    print(f"  Forensic data: {'available' if forensic else 'missing'}")
    print(f"  Policy history: {len(policy_history)} entries")
    print(f"  Learning history: {len(learning_history)} entries")
    
    # Build long-horizon plan
    print("\n[3/4] Synthesizing 45-day governance plan...")
    plan = build_long_horizon_plan(
        feedback, strategic, fusion, threshold_policy, rdgl,
        forensic, policy_history, learning_history
    )
    
    print(f"  Status: {plan['status']}")
    print(f"  MV-CRS Trend: {plan['mvcrs_health_trend']}")
    print(f"  Forensic Risk: {plan['forensic_risk_projection']:.3f}")
    print(f"  Policy Instability: {plan['predicted_policy_instability']:.3f}")
    print(f"  Trust Events: {plan['expected_trust_events']}")
    print(f"  Actions: {', '.join(plan['recommended_governance_actions'])}")
    print(f"  Confidence: {plan['confidence']:.3f}")
    
    # Write outputs
    print("\n[4/4] Writing long-horizon plan artifacts...")
    plan_ok = write_long_horizon_plan(plan)
    log_ok = append_hlgs_log(plan)
    
    if not (plan_ok and log_ok):
        print("\n✗ Critical: Persistent write failures detected", file=sys.stderr)
        create_fix_branch()
        update_audit_marker("CRITICAL")
        return 2
    
    # Update audit marker based on plan status
    if plan["status"] == "critical":
        if plan["confidence"] > 0.7:
            print("\n⚠ Critical status detected with high confidence", file=sys.stderr)
            update_audit_marker("CRITICAL")
            return 1  # Non-fatal, but signals attention needed
        else:
            print("\n⚠ Critical status detected with low confidence (monitoring)", file=sys.stderr)
            update_audit_marker("CRITICAL")
            # Return 0 for low-confidence critical (monitoring only)
    
    update_audit_marker("UPDATED")
    
    print("\n" + "=" * 60)
    print("✓ Long-horizon governance synthesizer completed successfully")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_hlgs_engine())
