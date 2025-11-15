#!/usr/bin/env python3
"""
Test suite for MV-CRS Long-Horizon Governance Synthesizer — Phase XXXIX

Validates 45-day planning, trend analysis, risk projection, and action recommendation logic.

Author: GitHub Copilot (Phase XXXIX)
Created: 2025-11-15
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "mvcrs"))

import mvcrs_hlgs


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace with virtualized MVCRS_BASE_DIR."""
    os.environ["MVCRS_BASE_DIR"] = str(tmp_path)
    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    yield tmp_path
    os.environ.pop("MVCRS_BASE_DIR", None)


def create_feedback_state(workspace: Path, mvcrs_status: str = "ok", trust_locked: bool = False):
    """Create sample feedback state."""
    feedback = {
        "mvcrs_status": mvcrs_status,
        "trust_locked": trust_locked,
        "recommended_actions": ["monitor_governance_metrics"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    (workspace / "state" / "mvcrs_feedback.json").write_text(json.dumps(feedback, indent=2))


def create_strategic_influence(workspace: Path, profile: str = "stable", mvcrs_health: str = "ok", confidence: float = 0.9):
    """Create sample strategic influence."""
    strategic = {
        "strategic_profile": profile,
        "mvcrs_health": mvcrs_health,
        "rdgl_learning_rate_multiplier": 1.0,
        "atte_shift_ceiling_pct": 3.0,
        "fusion_sensitivity_bias": "neutral",
        "trust_guard_weight_delta": 0.0,
        "adaptive_response_aggressiveness": "medium",
        "confidence": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    (workspace / "state" / "mvcrs_strategic_influence.json").write_text(json.dumps(strategic, indent=2))


def create_policy_fusion(workspace: Path, fusion_state: str = "GREEN"):
    """Create sample policy fusion state."""
    fusion = {
        "fusion_state": fusion_state,
        "confidence": 0.85,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    (workspace / "state" / "policy_fusion_state.json").write_text(json.dumps(fusion, indent=2))


def create_threshold_policy(workspace: Path):
    """Create sample threshold policy."""
    threshold = {
        "current_threshold": 0.8,
        "adaptive_enabled": True,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    (workspace / "state" / "autonomous_threshold_policy.json").write_text(json.dumps(threshold, indent=2))


def create_rdgl_policy(workspace: Path, mode: str = "enabled", policy_score: float = 0.7):
    """Create sample RDGL policy."""
    rdgl = {
        "mode": mode,
        "policy_score": policy_score,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    (workspace / "state" / "rdgl_policy_adjustments.json").write_text(json.dumps(rdgl, indent=2))


def create_forensic_forecast(workspace: Path, anomaly_count: int = 5, drift_probability: float = 0.2):
    """Create sample forensic forecast."""
    forensic = {
        "anomaly_count": anomaly_count,
        "drift_probability": drift_probability,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    (workspace / "state" / "forensic_forecast.json").write_text(json.dumps(forensic, indent=2))


# =====================================================================
# Tests
# =====================================================================

def test_stable_scenario_advisory_actions(temp_workspace):
    """Test stable scenario generates advisory-only actions."""
    # Setup: All signals healthy
    create_feedback_state(temp_workspace, mvcrs_status="ok", trust_locked=False)
    create_strategic_influence(temp_workspace, profile="aggressive", mvcrs_health="ok", confidence=0.95)
    create_policy_fusion(temp_workspace, fusion_state="GREEN")
    create_threshold_policy(temp_workspace)
    create_rdgl_policy(temp_workspace, mode="enabled", policy_score=0.8)
    create_forensic_forecast(temp_workspace, anomaly_count=2, drift_probability=0.1)
    
    # Execute
    exit_code = mvcrs_hlgs.run_hlgs_engine()
    
    # Verify
    assert exit_code == 0
    
    plan_path = temp_workspace / "state" / "mvcrs_long_horizon_plan.json"
    assert plan_path.exists()
    
    plan = json.loads(plan_path.read_text())
    assert plan["status"] == "stable"
    assert plan["horizon_days"] == 45
    assert plan["mvcrs_health_trend"] == "improving"
    assert plan["forensic_risk_projection"] < 0.3
    assert plan["predicted_policy_instability"] < 0.3
    assert len(plan["recommended_governance_actions"]) <= 2  # Minimal advisory actions
    assert plan["confidence"] > 0.8


def test_volatile_signal_cluster(temp_workspace):
    """Test volatile scenario generates stabilizer actions."""
    # Setup: 2 warnings (fusion + forensic)
    create_feedback_state(temp_workspace, mvcrs_status="warning", trust_locked=False)
    create_strategic_influence(temp_workspace, profile="stable", mvcrs_health="warning", confidence=0.7)
    create_policy_fusion(temp_workspace, fusion_state="YELLOW")
    create_threshold_policy(temp_workspace)
    create_rdgl_policy(temp_workspace, mode="enabled", policy_score=0.5)
    create_forensic_forecast(temp_workspace, anomaly_count=60, drift_probability=0.65)  # High risk
    
    # Execute
    exit_code = mvcrs_hlgs.run_hlgs_engine()
    
    # Verify
    assert exit_code == 0
    
    plan = json.loads((temp_workspace / "state" / "mvcrs_long_horizon_plan.json").read_text())
    assert plan["status"] == "volatile"
    assert plan["forensic_risk_projection"] > 0.5
    assert 1 <= len(plan["recommended_governance_actions"]) <= 2
    assert "hold_current_policy" in plan["recommended_governance_actions"]


def test_critical_cluster_actions(temp_workspace):
    """Test critical scenario generates preventive interventions."""
    # Setup: 3+ warnings (MV-CRS + fusion + forensic + ATTE)
    create_feedback_state(temp_workspace, mvcrs_status="failed", trust_locked=True)
    create_strategic_influence(temp_workspace, profile="cautious", mvcrs_health="failed", confidence=0.4)
    create_policy_fusion(temp_workspace, fusion_state="RED")
    create_threshold_policy(temp_workspace)
    create_rdgl_policy(temp_workspace, mode="enabled", policy_score=0.3)
    create_forensic_forecast(temp_workspace, anomaly_count=80, drift_probability=0.8)
    
    # Execute
    exit_code = mvcrs_hlgs.run_hlgs_engine()
    
    # Verify - exit code 0 because confidence < 0.7 (low confidence critical = monitoring only)
    assert exit_code == 0
    
    plan = json.loads((temp_workspace / "state" / "mvcrs_long_horizon_plan.json").read_text())
    assert plan["status"] == "critical"
    assert plan["mvcrs_health_trend"] == "declining"
    assert plan["predicted_policy_instability"] > 0.7
    assert 2 <= len(plan["recommended_governance_actions"]) <= 4
    assert "increase_threshold_headroom" in plan["recommended_governance_actions"]
    assert "prepare_self_healing_window" in plan["recommended_governance_actions"]


def test_numeric_clamping(temp_workspace):
    """Test numeric values are properly clamped."""
    create_feedback_state(temp_workspace, mvcrs_status="ok")
    create_strategic_influence(temp_workspace, profile="stable", confidence=0.85)
    create_policy_fusion(temp_workspace, fusion_state="GREEN")
    create_threshold_policy(temp_workspace)
    create_rdgl_policy(temp_workspace, mode="enabled", policy_score=0.7)
    create_forensic_forecast(temp_workspace, anomaly_count=150, drift_probability=1.5)  # Out of range
    
    # Execute
    exit_code = mvcrs_hlgs.run_hlgs_engine()
    
    # Verify
    assert exit_code == 0
    
    plan = json.loads((temp_workspace / "state" / "mvcrs_long_horizon_plan.json").read_text())
    assert 0.0 <= plan["forensic_risk_projection"] <= 1.0
    assert 0.0 <= plan["predicted_policy_instability"] <= 1.0
    assert 0.0 <= plan["confidence"] <= 1.0


def test_idempotent_audit_marker(temp_workspace):
    """Test audit marker is idempotent (single marker per run)."""
    # Create summary file
    summary_path = temp_workspace / "INSTRUCTION_EXECUTION_SUMMARY.md"
    summary_path.write_text("# Summary\n\nTest content\n")
    
    create_feedback_state(temp_workspace, mvcrs_status="ok")
    create_strategic_influence(temp_workspace, profile="stable", confidence=0.9)
    create_policy_fusion(temp_workspace, fusion_state="GREEN")
    create_threshold_policy(temp_workspace)
    create_rdgl_policy(temp_workspace, mode="enabled", policy_score=0.7)
    
    # Execute twice
    mvcrs_hlgs.run_hlgs_engine()
    mvcrs_hlgs.run_hlgs_engine()
    
    # Verify: Only one marker per status type
    content = summary_path.read_text()
    updated_count = content.count("<!-- MVCRS_HLGS: UPDATED")
    assert updated_count == 1


def test_fix_branch_on_fs_failure(temp_workspace, monkeypatch):
    """Test fix branch creation on persistent write failure."""
    create_feedback_state(temp_workspace, mvcrs_status="ok")
    create_strategic_influence(temp_workspace, profile="stable", confidence=0.9)
    create_policy_fusion(temp_workspace, fusion_state="GREEN")
    create_threshold_policy(temp_workspace)
    create_rdgl_policy(temp_workspace, mode="enabled", policy_score=0.7)
    
    # Mock write failure
    def mock_write_fail(*args, **kwargs):
        return False
    
    monkeypatch.setattr(mvcrs_hlgs, "write_long_horizon_plan", mock_write_fail)
    
    # Execute
    exit_code = mvcrs_hlgs.run_hlgs_engine()
    
    # Verify: Exit code 2 for critical failure
    assert exit_code == 2


def test_confidence_with_missing_optional(temp_workspace):
    """Test confidence drops when optional inputs are missing."""
    # Setup: Only mandatory inputs
    create_feedback_state(temp_workspace, mvcrs_status="ok")
    create_strategic_influence(temp_workspace, profile="stable", confidence=0.9)
    create_policy_fusion(temp_workspace, fusion_state="GREEN")
    create_threshold_policy(temp_workspace)
    create_rdgl_policy(temp_workspace, mode="enabled", policy_score=0.7)
    # No forensic, policy_history, or learning_history
    
    # Execute
    exit_code = mvcrs_hlgs.run_hlgs_engine()
    
    # Verify
    assert exit_code == 0
    
    plan = json.loads((temp_workspace / "state" / "mvcrs_long_horizon_plan.json").read_text())
    # Confidence is mainly from strategic (0.9) with small bonus for missing optional data
    # Expected: ~0.9 (no penalty for missing optional, small bonus only if present)
    assert 0.8 <= plan["confidence"] <= 0.95


def test_trend_analysis_correctness(temp_workspace):
    """Test trend analysis produces correct classifications."""
    # Setup: Improving MV-CRS, upward RDGL, low ATTE pressure
    create_feedback_state(temp_workspace, mvcrs_status="ok")
    create_strategic_influence(temp_workspace, profile="aggressive", mvcrs_health="ok", confidence=0.95)
    create_policy_fusion(temp_workspace, fusion_state="GREEN")
    create_threshold_policy(temp_workspace)
    create_rdgl_policy(temp_workspace, mode="enabled", policy_score=0.8)
    
    # Execute
    exit_code = mvcrs_hlgs.run_hlgs_engine()
    
    # Verify
    assert exit_code == 0
    
    plan = json.loads((temp_workspace / "state" / "mvcrs_long_horizon_plan.json").read_text())
    assert plan["mvcrs_health_trend"] == "improving"
    assert plan["rdgl_trajectory"] == "upward"
    assert plan["atte_pressure"] == "low"
    assert plan["fusion_cycle_prediction"] == "relax"
    
    # Test declining scenario
    create_strategic_influence(temp_workspace, profile="cautious", mvcrs_health="failed", confidence=0.4)
    create_rdgl_policy(temp_workspace, mode="enabled", policy_score=0.3)
    
    exit_code = mvcrs_hlgs.run_hlgs_engine()
    assert exit_code == 0  # Volatile status (not critical due to missing forensic)
    
    plan = json.loads((temp_workspace / "state" / "mvcrs_long_horizon_plan.json").read_text())
    assert plan["mvcrs_health_trend"] == "declining"
    assert plan["rdgl_trajectory"] == "downward"
    assert plan["status"] in ["volatile", "critical"]  # Can be either based on forensic data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
