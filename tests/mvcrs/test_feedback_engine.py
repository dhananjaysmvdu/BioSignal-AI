#!/usr/bin/env python3
"""
Test suite for MV-CRS Feedback Engine — Phase XXXVII

Validates feedback computation logic, decision rules, confidence scoring,
atomic writes, idempotent markers, and fix-branch creation.

Author: GitHub Copilot (Phase XXXVII)
Created: 2025-11-15
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for importing feedback engine
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.mvcrs import mvcrs_feedback_engine


@pytest.fixture
def feedback_sandbox(tmp_path):
    """Create isolated test environment with MVCRS_BASE_DIR virtualization."""
    sandbox = tmp_path / "feedback_test"
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


def write_integration_state(sandbox: Path, final_decision: str, mvcrs_core_ok: bool, 
                            escalation_open: bool, governance_risk: str):
    """Helper to write integration state fixture."""
    state = {
        "final_decision": final_decision,
        "mvcrs_core_ok": mvcrs_core_ok,
        "escalation_open": escalation_open,
        "governance_risk_level": governance_risk,
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
    path = sandbox / "state" / "mvcrs_integration_state.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def write_verifier_state(sandbox: Path, status: str):
    """Helper to write verifier state fixture."""
    state = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    path = sandbox / "state" / "challenge_verifier_state.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def write_execution_summary(sandbox: Path):
    """Helper to write execution summary for audit marker tests."""
    path = sandbox / "INSTRUCTION_EXECUTION_SUMMARY.md"
    content = "# Execution Summary\n\nTest document for audit markers.\n"
    path.write_text(content, encoding="utf-8")


# =====================================================================
# Test 1: OK Status → Relaxation Shift, Reinforce Signal, Lower Bias
# =====================================================================

def test_ok_status_relaxation_reinforce_lower(feedback_sandbox):
    """
    Test feedback when MV-CRS is healthy (ok status).
    
    Expectations:
    - mvcrs_status = "ok"
    - threshold_shift = -1% (relaxation)
    - rdgl_signal = "reinforce"
    - fusion_bias = "lower"
    """
    write_integration_state(feedback_sandbox, "allow", True, False, "green")
    write_verifier_state(feedback_sandbox, "CHALLENGE_PASSED")
    write_execution_summary(feedback_sandbox)
    
    # Run feedback engine
    exit_code = mvcrs_feedback_engine.run_feedback_engine()
    
    # Verify success
    assert exit_code == 0
    
    # Load feedback output
    feedback_path = feedback_sandbox / "state" / "mvcrs_feedback.json"
    assert feedback_path.exists()
    
    with open(feedback_path, "r", encoding="utf-8") as f:
        feedback = json.load(f)
    
    # Validate feedback object
    assert feedback["mvcrs_status"] == "ok"
    assert feedback["recommended_threshold_shift_pct"] == -1.0
    assert feedback["rdgl_signal"] == "reinforce"
    assert feedback["recommended_fusion_bias"] == "lower"
    assert feedback["feedback_confidence"] > 0.5
    assert "timestamp" in feedback


# =====================================================================
# Test 2: Warning Status → +1 Shift, Neutral Signal
# =====================================================================

def test_warning_status_shift_neutral(feedback_sandbox):
    """
    Test feedback when MV-CRS has warnings (escalation open but core ok).
    
    Expectations:
    - mvcrs_status = "warning"
    - threshold_shift = +1% (caution)
    - rdgl_signal = "neutral"
    """
    write_integration_state(feedback_sandbox, "restricted", True, True, "green")
    write_verifier_state(feedback_sandbox, "CHALLENGE_PASSED")
    write_execution_summary(feedback_sandbox)
    
    # Run feedback engine
    exit_code = mvcrs_feedback_engine.run_feedback_engine()
    
    assert exit_code == 0
    
    feedback_path = feedback_sandbox / "state" / "mvcrs_feedback.json"
    with open(feedback_path, "r", encoding="utf-8") as f:
        feedback = json.load(f)
    
    assert feedback["mvcrs_status"] == "warning"
    assert feedback["recommended_threshold_shift_pct"] == 1.0
    assert feedback["rdgl_signal"] == "neutral"


# =====================================================================
# Test 3: Failed Status → +3 Shift, Penalize Signal, Raise Bias
# =====================================================================

def test_failed_status_tighten_penalize_raise(feedback_sandbox):
    """
    Test feedback when MV-CRS has failures (core not ok).
    
    Expectations:
    - mvcrs_status = "failed"
    - threshold_shift = +3% (tightening)
    - rdgl_signal = "penalize"
    - fusion_bias = "raise"
    """
    write_integration_state(feedback_sandbox, "blocked", False, False, "red")
    write_verifier_state(feedback_sandbox, "CHALLENGE_FAILED")
    write_execution_summary(feedback_sandbox)
    
    exit_code = mvcrs_feedback_engine.run_feedback_engine()
    
    assert exit_code == 0
    
    feedback_path = feedback_sandbox / "state" / "mvcrs_feedback.json"
    with open(feedback_path, "r", encoding="utf-8") as f:
        feedback = json.load(f)
    
    assert feedback["mvcrs_status"] == "failed"
    assert feedback["recommended_threshold_shift_pct"] == 3.0
    assert feedback["rdgl_signal"] == "penalize"
    assert feedback["recommended_fusion_bias"] == "raise"


# =====================================================================
# Test 4: Escalation Open → Always Bias="Raise"
# =====================================================================

def test_escalation_open_always_raise_bias(feedback_sandbox):
    """
    Test that escalation_open=true always forces fusion_bias="raise".
    
    Even if MV-CRS core is ok, escalation presence should escalate bias.
    """
    write_integration_state(feedback_sandbox, "restricted", True, True, "yellow")
    write_verifier_state(feedback_sandbox, "CHALLENGE_PASSED")
    write_execution_summary(feedback_sandbox)
    
    exit_code = mvcrs_feedback_engine.run_feedback_engine()
    
    assert exit_code == 0
    
    feedback_path = feedback_sandbox / "state" / "mvcrs_feedback.json"
    with open(feedback_path, "r", encoding="utf-8") as f:
        feedback = json.load(f)
    
    # Fusion bias must be "raise" due to escalation_open
    assert feedback["escalation_open"] is True
    assert feedback["recommended_fusion_bias"] == "raise"


# =====================================================================
# Test 5: Confidence Drops <0.5 When Signals Inconsistent
# =====================================================================

def test_confidence_drops_on_inconsistent_signals(feedback_sandbox):
    """
    Test that confidence score decreases when signals are contradictory.
    
    Scenario: mvcrs_core_ok=True but verifier status=CHALLENGE_FAILED
    """
    write_integration_state(feedback_sandbox, "allow", True, False, "green")
    write_verifier_state(feedback_sandbox, "CHALLENGE_FAILED")  # Contradictory
    write_execution_summary(feedback_sandbox)
    
    exit_code = mvcrs_feedback_engine.run_feedback_engine()
    
    assert exit_code == 0
    
    feedback_path = feedback_sandbox / "state" / "mvcrs_feedback.json"
    with open(feedback_path, "r", encoding="utf-8") as f:
        feedback = json.load(f)
    
    # Confidence should drop below 0.5 due to contradictory signals
    assert feedback["feedback_confidence"] < 0.5


# =====================================================================
# Test 6: Idempotent Audit Marker
# =====================================================================

def test_idempotent_audit_marker(feedback_sandbox):
    """
    Test that audit marker is idempotent (single marker on multiple runs).
    """
    write_integration_state(feedback_sandbox, "allow", True, False, "green")
    write_verifier_state(feedback_sandbox, "CHALLENGE_PASSED")
    write_execution_summary(feedback_sandbox)
    
    # First run
    exit_code1 = mvcrs_feedback_engine.run_feedback_engine()
    assert exit_code1 == 0
    
    summary_path = feedback_sandbox / "INSTRUCTION_EXECUTION_SUMMARY.md"
    content1 = summary_path.read_text(encoding="utf-8")
    marker_count1 = content1.count("<!-- MVCRS_FEEDBACK:")
    
    # Second run
    exit_code2 = mvcrs_feedback_engine.run_feedback_engine()
    assert exit_code2 == 0
    
    content2 = summary_path.read_text(encoding="utf-8")
    marker_count2 = content2.count("<!-- MVCRS_FEEDBACK:")
    
    # Should have exactly one marker after both runs
    assert marker_count1 == 1
    assert marker_count2 == 1


# =====================================================================
# Test 7: Fix-Branch Creation on Repeated FS Failure
# =====================================================================

def test_fix_branch_on_persistent_write_failure(feedback_sandbox):
    """
    Test that persistent write failures trigger fix-branch creation.
    
    Mock file writes to fail repeatedly, verify exit code 2 and
    fix-branch creation attempt.
    """
    write_integration_state(feedback_sandbox, "allow", True, False, "green")
    write_verifier_state(feedback_sandbox, "CHALLENGE_PASSED")
    write_execution_summary(feedback_sandbox)
    
    # Mock write_feedback_state to always fail
    with patch.object(mvcrs_feedback_engine, 'write_feedback_state', return_value=False):
        with patch.object(mvcrs_feedback_engine, 'create_fix_branch') as mock_fix_branch:
            exit_code = mvcrs_feedback_engine.run_feedback_engine()
            
            # Should return exit code 2 (critical failure)
            assert exit_code == 2
            
            # Verify fix-branch creation was attempted
            mock_fix_branch.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
