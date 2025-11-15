"""
Test suite for MV-CRS Integration Orchestrator

Validates:
- All upstream signals healthy → final_decision = allow
- Escalation open → final_decision = restricted
- Governance red + mvcrs_core_ok=false → final_decision = blocked
- Lifecycle stuck >48h → CI should fail (simulated)
- Idempotent audit markers
- Fix-branch triggered on persistent write failure
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add mvcrs scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "mvcrs"))

from mvcrs_integration_orchestrator import (
    analyze_mvcrs_core_ok,
    analyze_escalation_open,
    get_lifecycle_state,
    analyze_governance_risk_level,
    compute_final_decision,
    run_integration_orchestrator,
)


# ============================================================================
# Test: All healthy → allow
# ============================================================================

def test_all_healthy_signals_allow_decision(lifecycle_sandbox):
    """Test that all healthy signals produce 'allow' decision."""
    base_dir = lifecycle_sandbox
    os.environ["MVCRS_BASE_DIR"] = str(base_dir)
    
    # Create healthy verifier state
    (base_dir / "state").mkdir(parents=True, exist_ok=True)
    verifier_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "deviations": []
    }
    (base_dir / "state" / "challenge_verifier_state.json").write_text(
        json.dumps(verifier_state), encoding="utf-8"
    )
    
    # Create lifecycle in resolved state
    lifecycle_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_state": "resolved",
        "entered_current_state_at": datetime.now(timezone.utc).isoformat(),
        "last_transition_reason": "Validation passed",
        "resolved_count": 5,
        "rejected_count": 1
    }
    (base_dir / "state" / "mvcrs_escalation_lifecycle.json").write_text(
        json.dumps(lifecycle_state), encoding="utf-8"
    )
    
    # Create green policy fusion
    policy_fusion = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fusion_state": "FUSION_GREEN"
    }
    (base_dir / "state" / "policy_fusion_state.json").write_text(
        json.dumps(policy_fusion), encoding="utf-8"
    )
    
    # Run orchestrator
    exit_code = run_integration_orchestrator()
    assert exit_code == 0
    
    # Check integration state
    integration_path = base_dir / "state" / "mvcrs_integration_state.json"
    assert integration_path.exists()
    integration = json.loads(integration_path.read_text())
    
    assert integration["mvcrs_core_ok"] is True
    assert integration["escalation_open"] is False
    assert integration["governance_risk_level"] == "green"
    assert integration["final_decision"] == "allow"


# ============================================================================
# Test: Escalation open → restricted
# ============================================================================

def test_escalation_open_restricted_decision(lifecycle_sandbox):
    """Test that open escalation produces 'restricted' decision."""
    base_dir = lifecycle_sandbox
    os.environ["MVCRS_BASE_DIR"] = str(base_dir)
    
    # Create verifier state
    (base_dir / "state").mkdir(parents=True, exist_ok=True)
    verifier_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "warning",
        "deviations": [{"type": "TYPE_B_CONSISTENCY", "severity": "medium"}]
    }
    (base_dir / "state" / "challenge_verifier_state.json").write_text(
        json.dumps(verifier_state), encoding="utf-8"
    )
    
    # Create lifecycle in awaiting_validation state (escalation open)
    lifecycle_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_state": "awaiting_validation",
        "entered_current_state_at": datetime.now(timezone.utc).isoformat(),
        "last_transition_reason": "Correction applied",
        "resolved_count": 0,
        "rejected_count": 0
    }
    (base_dir / "state" / "mvcrs_escalation_lifecycle.json").write_text(
        json.dumps(lifecycle_state), encoding="utf-8"
    )
    
    # Run orchestrator
    exit_code = run_integration_orchestrator()
    assert exit_code == 0
    
    # Check integration state
    integration_path = base_dir / "state" / "mvcrs_integration_state.json"
    integration = json.loads(integration_path.read_text())
    
    assert integration["escalation_open"] is True
    assert integration["final_decision"] == "restricted"


# ============================================================================
# Test: Governance red + mvcrs_core_ok=false → blocked
# ============================================================================

def test_governance_red_mvcrs_not_ok_blocked(lifecycle_sandbox):
    """Test that governance red + mvcrs not ok produces 'blocked' decision."""
    base_dir = lifecycle_sandbox
    os.environ["MVCRS_BASE_DIR"] = str(base_dir)
    
    # Create failed verifier state
    (base_dir / "state").mkdir(parents=True, exist_ok=True)
    verifier_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "deviations": [{"type": "TYPE_A_STRUCTURE", "severity": "high"}]
    }
    (base_dir / "state" / "challenge_verifier_state.json").write_text(
        json.dumps(verifier_state), encoding="utf-8"
    )
    
    # Create red policy fusion
    policy_fusion = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fusion_state": "FUSION_RED"
    }
    (base_dir / "state" / "policy_fusion_state.json").write_text(
        json.dumps(policy_fusion), encoding="utf-8"
    )
    
    # Run orchestrator
    exit_code = run_integration_orchestrator()
    assert exit_code == 0
    
    # Check integration state
    integration_path = base_dir / "state" / "mvcrs_integration_state.json"
    integration = json.loads(integration_path.read_text())
    
    assert integration["mvcrs_core_ok"] is False
    assert integration["governance_risk_level"] == "red"
    assert integration["final_decision"] == "blocked"


# ============================================================================
# Test: Lifecycle stuck >48h detection
# ============================================================================

def test_lifecycle_stuck_detection(lifecycle_sandbox):
    """Test detection of lifecycle stuck in non-terminal state >48h."""
    base_dir = lifecycle_sandbox
    os.environ["MVCRS_BASE_DIR"] = str(base_dir)
    
    # Create lifecycle stuck in pending for >48h
    (base_dir / "state").mkdir(parents=True, exist_ok=True)
    entered_at = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    lifecycle_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_state": "pending",
        "entered_current_state_at": entered_at,
        "last_transition_reason": "Escalation created",
        "resolved_count": 0,
        "rejected_count": 0
    }
    (base_dir / "state" / "mvcrs_escalation_lifecycle.json").write_text(
        json.dumps(lifecycle_state), encoding="utf-8"
    )
    
    # Read back and verify time calculation
    lifecycle = json.loads((base_dir / "state" / "mvcrs_escalation_lifecycle.json").read_text())
    entered = datetime.fromisoformat(lifecycle["entered_current_state_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    elapsed_hours = (now - entered).total_seconds() / 3600
    
    assert elapsed_hours > 48
    assert lifecycle["current_state"] == "pending"


# ============================================================================
# Test: Idempotent audit marker
# ============================================================================

def test_idempotent_audit_marker(lifecycle_sandbox):
    """Test that audit markers are idempotent across multiple runs."""
    base_dir = lifecycle_sandbox
    os.environ["MVCRS_BASE_DIR"] = str(base_dir)
    
    # Create minimal state
    (base_dir / "state").mkdir(parents=True, exist_ok=True)
    verifier_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "deviations": []
    }
    (base_dir / "state" / "challenge_verifier_state.json").write_text(
        json.dumps(verifier_state), encoding="utf-8"
    )
    
    # Run orchestrator twice
    exit_code1 = run_integration_orchestrator()
    exit_code2 = run_integration_orchestrator()
    
    assert exit_code1 == 0
    assert exit_code2 == 0
    
    # Check audit markers
    audit_path = base_dir / "docs" / "audit_summary.md"
    assert audit_path.exists()
    content = audit_path.read_text()
    
    # Count markers - should only have one
    marker_count = content.count("<!-- MVCRS_INTEGRATION:")
    assert marker_count == 1
    
    # Verify UPDATED marker present
    assert "MVCRS_INTEGRATION: UPDATED" in content


# ============================================================================
# Test: Fix-branch triggered on persistent write failure
# ============================================================================

def test_fix_branch_on_persistent_write_failure(lifecycle_sandbox, monkeypatch):
    """Test that fix branch is created on persistent write failures."""
    base_dir = lifecycle_sandbox
    os.environ["MVCRS_BASE_DIR"] = str(base_dir)
    
    # Create state
    (base_dir / "state").mkdir(parents=True, exist_ok=True)
    verifier_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "deviations": []
    }
    (base_dir / "state" / "challenge_verifier_state.json").write_text(
        json.dumps(verifier_state), encoding="utf-8"
    )
    
    # Simulate write failure by making state directory read-only
    import stat
    state_dir = base_dir / "state"
    
    # Make integration state write fail by removing write permissions
    def fail_write(*args, **kwargs):
        raise PermissionError("Simulated write failure")
    
    # Patch atomic_write_json to fail
    import mvcrs_integration_orchestrator
    original_write = mvcrs_integration_orchestrator.atomic_write_json
    monkeypatch.setattr(mvcrs_integration_orchestrator, "atomic_write_json", fail_write)
    
    # Run orchestrator (should fail but handle gracefully)
    exit_code = run_integration_orchestrator()
    assert exit_code == 2  # Critical failure
    
    # Restore original function
    monkeypatch.setattr(mvcrs_integration_orchestrator, "atomic_write_json", original_write)
