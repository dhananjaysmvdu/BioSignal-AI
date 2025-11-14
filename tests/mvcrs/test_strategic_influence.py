#!/usr/bin/env python3
"""
Test suite for MV-CRS Strategic Influence Engine — Phase XXXVIII

Validates strategic profile computation, numeric clamping, confidence scoring,
atomic writes, idempotent markers, and fix-branch creation.

Author: GitHub Copilot (Phase XXXVIII)
Created: 2025-11-15
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

# Add parent directory to path for importing strategic influence engine
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.mvcrs import mvcrs_strategic_influence


@pytest.fixture
def strategic_sandbox(tmp_path):
    """Create isolated test environment with MVCRS_BASE_DIR virtualization."""
    sandbox = tmp_path / "strategic_test"
    sandbox.mkdir()
    
    # Create directory structure
    (sandbox / "state").mkdir()
    (sandbox / "logs").mkdir()
    
    # Set environment variable for path virtualization
    os.environ["MVCRS_BASE_DIR"] = str(sandbox)
    
    yield sandbox
    
    # Cleanup
    if "MVCRS_BASE_DIR" in os.environ:
        del os.environ["MVCRS_BASE_DIR"]


def write_feedback_state(sandbox: Path, mvcrs_status: str, feedback_confidence: float = 0.9):
    """Helper to write feedback state fixture."""
    state = {
        "mvcrs_status": mvcrs_status,
        "feedback_confidence": feedback_confidence,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    path = sandbox / "state" / "mvcrs_feedback.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def write_trust_lock_state(sandbox: Path, trust_locked: bool):
    """Helper to write trust lock state fixture."""
    state = {
        "trust_locked": trust_locked,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    path = sandbox / "state" / "trust_lock_state.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def write_policy_fusion_state(sandbox: Path, fusion_state: str):
    """Helper to write policy fusion state fixture."""
    state = {
        "fusion_state": fusion_state,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    path = sandbox / "state" / "policy_fusion_state.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def write_minimal_governance_states(sandbox: Path):
    """Helper to write minimal RDGL and threshold policy states."""
    # RDGL policy
    rdgl_path = sandbox / "state" / "rdgl_policy_adjustments.json"
    with open(rdgl_path, "w", encoding="utf-8") as f:
        json.dump({"mode": "active"}, f)
    
    # Threshold policy
    threshold_path = sandbox / "state" / "autonomous_threshold_policy.json"
    with open(threshold_path, "w", encoding="utf-8") as f:
        json.dump({"max_shift_pct": 3.0}, f)


def write_execution_summary(sandbox: Path):
    """Helper to write execution summary for audit marker tests."""
    path = sandbox / "INSTRUCTION_EXECUTION_SUMMARY.md"
    content = "# Execution Summary\n\nTest document for audit markers.\n"
    path.write_text(content, encoding="utf-8")


# =====================================================================
# Test 1: Failed → Cautious Profile + Tightening + High Aggressiveness
# =====================================================================

def test_failed_status_cautious_profile(strategic_sandbox):
    """
    Test strategic influence when MV-CRS status is failed.
    
    Expectations:
    - strategic_profile = "cautious"
    - rdgl_learning_rate_multiplier = 0.6
    - atte_shift_ceiling_pct reduced by 40% (1.8%)
    - fusion_sensitivity_bias = "tighten"
    - trust_guard_weight_delta = +0.05
    - adaptive_response_aggressiveness = "high"
    """
    write_feedback_state(strategic_sandbox, "failed")
    write_trust_lock_state(strategic_sandbox, False)
    write_policy_fusion_state(strategic_sandbox, "YELLOW")
    write_minimal_governance_states(strategic_sandbox)
    write_execution_summary(strategic_sandbox)
    
    # Run strategic influence engine
    exit_code = mvcrs_strategic_influence.run_strategic_influence_engine()
    
    assert exit_code == 0
    
    # Load strategic influence output
    sib_path = strategic_sandbox / "state" / "mvcrs_strategic_influence.json"
    assert sib_path.exists()
    
    with open(sib_path, "r", encoding="utf-8") as f:
        sib = json.load(f)
    
    # Validate strategic influence block
    assert sib["mvcrs_health"] == "failed"
    assert sib["strategic_profile"] == "cautious"
    assert sib["rdgl_learning_rate_multiplier"] == 0.6
    assert sib["atte_shift_ceiling_pct"] == 1.8  # 3.0 * 0.6
    assert sib["fusion_sensitivity_bias"] == "tighten"
    assert sib["trust_guard_weight_delta"] == 0.05
    assert sib["adaptive_response_aggressiveness"] == "high"
    assert sib["confidence"] > 0.5


# =====================================================================
# Test 2: Warning → Stable Profile + Neutral Bias
# =====================================================================

def test_warning_status_stable_profile(strategic_sandbox):
    """
    Test strategic influence when MV-CRS status is warning.
    
    Expectations:
    - strategic_profile = "stable"
    - rdgl_learning_rate_multiplier = 0.9
    - atte_shift_ceiling_pct reduced by 15% (2.55%)
    - fusion_sensitivity_bias = "neutral"
    - adaptive_response_aggressiveness = "medium"
    """
    write_feedback_state(strategic_sandbox, "warning")
    write_trust_lock_state(strategic_sandbox, False)
    write_policy_fusion_state(strategic_sandbox, "GREEN")
    write_minimal_governance_states(strategic_sandbox)
    write_execution_summary(strategic_sandbox)
    
    exit_code = mvcrs_strategic_influence.run_strategic_influence_engine()
    
    assert exit_code == 0
    
    sib_path = strategic_sandbox / "state" / "mvcrs_strategic_influence.json"
    with open(sib_path, "r", encoding="utf-8") as f:
        sib = json.load(f)
    
    assert sib["mvcrs_health"] == "warning"
    assert sib["strategic_profile"] == "stable"
    assert sib["rdgl_learning_rate_multiplier"] == 0.9
    assert sib["atte_shift_ceiling_pct"] == 2.55  # 3.0 * 0.85
    assert sib["fusion_sensitivity_bias"] == "neutral"
    assert sib["adaptive_response_aggressiveness"] == "medium"


# =====================================================================
# Test 3: OK → Aggressive Profile + Relax Bias
# =====================================================================

def test_ok_status_aggressive_profile(strategic_sandbox):
    """
    Test strategic influence when MV-CRS status is ok.
    
    Expectations:
    - strategic_profile = "aggressive"
    - rdgl_learning_rate_multiplier = 1.1
    - atte_shift_ceiling_pct increased by 20% (3.6%)
    - fusion_sensitivity_bias = "relax"
    - trust_guard_weight_delta = -0.03
    - adaptive_response_aggressiveness = "low"
    """
    write_feedback_state(strategic_sandbox, "ok")
    write_trust_lock_state(strategic_sandbox, False)
    write_policy_fusion_state(strategic_sandbox, "GREEN")
    write_minimal_governance_states(strategic_sandbox)
    write_execution_summary(strategic_sandbox)
    
    exit_code = mvcrs_strategic_influence.run_strategic_influence_engine()
    
    assert exit_code == 0
    
    sib_path = strategic_sandbox / "state" / "mvcrs_strategic_influence.json"
    with open(sib_path, "r", encoding="utf-8") as f:
        sib = json.load(f)
    
    assert sib["mvcrs_health"] == "ok"
    assert sib["strategic_profile"] == "aggressive"
    assert sib["rdgl_learning_rate_multiplier"] == 1.1
    assert sib["atte_shift_ceiling_pct"] == 3.6  # 3.0 * 1.2
    assert sib["fusion_sensitivity_bias"] == "relax"
    assert sib["trust_guard_weight_delta"] == -0.03
    assert sib["adaptive_response_aggressiveness"] == "low"


# =====================================================================
# Test 4: Numeric Clamps Applied
# =====================================================================

def test_numeric_clamps_applied(strategic_sandbox):
    """
    Test that numeric values are clamped to safe ranges.
    
    Verifies:
    - rdgl_learning_rate_multiplier ∈ [0.5, 1.5]
    - atte_shift_ceiling_pct ∈ [1.0, 5.0]
    - trust_guard_weight_delta ∈ [-0.10, +0.10]
    """
    write_feedback_state(strategic_sandbox, "ok")
    write_trust_lock_state(strategic_sandbox, False)
    write_policy_fusion_state(strategic_sandbox, "GREEN")
    write_minimal_governance_states(strategic_sandbox)
    write_execution_summary(strategic_sandbox)
    
    exit_code = mvcrs_strategic_influence.run_strategic_influence_engine()
    
    assert exit_code == 0
    
    sib_path = strategic_sandbox / "state" / "mvcrs_strategic_influence.json"
    with open(sib_path, "r", encoding="utf-8") as f:
        sib = json.load(f)
    
    # Verify clamping
    assert 0.5 <= sib["rdgl_learning_rate_multiplier"] <= 1.5
    assert 1.0 <= sib["atte_shift_ceiling_pct"] <= 5.0
    assert -0.10 <= sib["trust_guard_weight_delta"] <= 0.10


# =====================================================================
# Test 5: Idempotent Audit Marker
# =====================================================================

def test_idempotent_audit_marker(strategic_sandbox):
    """
    Test that audit marker is idempotent (single marker on multiple runs).
    """
    write_feedback_state(strategic_sandbox, "ok")
    write_trust_lock_state(strategic_sandbox, False)
    write_policy_fusion_state(strategic_sandbox, "GREEN")
    write_minimal_governance_states(strategic_sandbox)
    write_execution_summary(strategic_sandbox)
    
    # First run
    exit_code1 = mvcrs_strategic_influence.run_strategic_influence_engine()
    assert exit_code1 == 0
    
    summary_path = strategic_sandbox / "INSTRUCTION_EXECUTION_SUMMARY.md"
    content1 = summary_path.read_text(encoding="utf-8")
    marker_count1 = content1.count("<!-- MVCRS_STRATEGIC_INFLUENCE:")
    
    # Second run
    exit_code2 = mvcrs_strategic_influence.run_strategic_influence_engine()
    assert exit_code2 == 0
    
    content2 = summary_path.read_text(encoding="utf-8")
    marker_count2 = content2.count("<!-- MVCRS_STRATEGIC_INFLUENCE:")
    
    # Should have exactly one marker after both runs
    assert marker_count1 == 1
    assert marker_count2 == 1


# =====================================================================
# Test 6: Fix-Branch Creation on Repeated FS Failure
# =====================================================================

def test_fix_branch_on_persistent_write_failure(strategic_sandbox):
    """
    Test that persistent write failures trigger fix-branch creation.
    
    Mock file writes to fail repeatedly, verify exit code 2 and
    fix-branch creation attempt.
    """
    write_feedback_state(strategic_sandbox, "ok")
    write_trust_lock_state(strategic_sandbox, False)
    write_policy_fusion_state(strategic_sandbox, "GREEN")
    write_minimal_governance_states(strategic_sandbox)
    write_execution_summary(strategic_sandbox)
    
    # Mock write_strategic_influence_state to always fail
    with patch.object(mvcrs_strategic_influence, 'write_strategic_influence_state', return_value=False):
        with patch.object(mvcrs_strategic_influence, 'create_fix_branch') as mock_fix_branch:
            exit_code = mvcrs_strategic_influence.run_strategic_influence_engine()
            
            # Should return exit code 2 (critical failure)
            assert exit_code == 2
            
            # Verify fix-branch creation was attempted
            mock_fix_branch.assert_called_once()


# =====================================================================
# Test 7: Confidence Scoring Reacts to Missing/Stale Artifacts
# =====================================================================

def test_confidence_drops_on_missing_states(strategic_sandbox):
    """
    Test that confidence score decreases when governance states are missing.
    
    Scenario: Only feedback state present, all other states missing.
    """
    write_feedback_state(strategic_sandbox, "ok", feedback_confidence=0.9)
    write_execution_summary(strategic_sandbox)
    # Intentionally omit trust_lock, fusion, rdgl, threshold states
    
    exit_code = mvcrs_strategic_influence.run_strategic_influence_engine()
    
    assert exit_code == 0
    
    sib_path = strategic_sandbox / "state" / "mvcrs_strategic_influence.json"
    with open(sib_path, "r", encoding="utf-8") as f:
        sib = json.load(f)
    
    # Confidence should be reduced due to missing states
    # 4 missing states × 0.15 penalty = 0.6 multiplier
    # 0.9 (feedback) × 0.6 (missing) ≈ 0.54
    assert sib["confidence"] < 0.7


# =====================================================================
# Test 8: Strategic Profile Influences RDGL Multiplier Range
# =====================================================================

def test_strategic_profile_influences_rdgl_multiplier(strategic_sandbox):
    """
    Test that strategic profile correctly maps to RDGL multiplier ranges.
    
    Verifies:
    - cautious → 0.6 (slow learning)
    - stable → 0.9 (conservative)
    - aggressive → 1.1 (accelerated)
    """
    # Test cautious
    write_feedback_state(strategic_sandbox, "failed")
    write_trust_lock_state(strategic_sandbox, False)
    write_policy_fusion_state(strategic_sandbox, "YELLOW")
    write_minimal_governance_states(strategic_sandbox)
    write_execution_summary(strategic_sandbox)
    
    exit_code = mvcrs_strategic_influence.run_strategic_influence_engine()
    assert exit_code == 0
    
    sib_path = strategic_sandbox / "state" / "mvcrs_strategic_influence.json"
    with open(sib_path, "r", encoding="utf-8") as f:
        sib_cautious = json.load(f)
    
    assert sib_cautious["strategic_profile"] == "cautious"
    assert sib_cautious["rdgl_learning_rate_multiplier"] == 0.6
    
    # Test stable
    write_feedback_state(strategic_sandbox, "warning")
    exit_code = mvcrs_strategic_influence.run_strategic_influence_engine()
    assert exit_code == 0
    
    with open(sib_path, "r", encoding="utf-8") as f:
        sib_stable = json.load(f)
    
    assert sib_stable["strategic_profile"] == "stable"
    assert sib_stable["rdgl_learning_rate_multiplier"] == 0.9
    
    # Test aggressive
    write_feedback_state(strategic_sandbox, "ok")
    write_policy_fusion_state(strategic_sandbox, "GREEN")
    exit_code = mvcrs_strategic_influence.run_strategic_influence_engine()
    assert exit_code == 0
    
    with open(sib_path, "r", encoding="utf-8") as f:
        sib_aggressive = json.load(f)
    
    assert sib_aggressive["strategic_profile"] == "aggressive"
    assert sib_aggressive["rdgl_learning_rate_multiplier"] == 1.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
