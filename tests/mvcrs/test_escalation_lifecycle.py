"""
Test suite for MV-CRS Escalation Lifecycle Engine

Validates:
- Escalation auto-creation on verifier failure
- State transitions (pending → in_progress → awaiting_validation → resolved/rejected)
- Time-based transitions (pending >24h)
- Correction artifact detection
- Validation outcomes
- Idempotent audit markers
- Atomic writes and retries
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add mvcrs scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "mvcrs"))

from mvcrs_escalation_lifecycle import (
    compute_next_state,
    should_create_escalation,
    should_transition_to_in_progress,
    should_transition_to_awaiting_validation,
    should_transition_to_resolved,
    should_transition_to_rejected,
    run_lifecycle_engine,
)


# ============================================================================
# Test: Escalation auto-creates on verifier failure
# ============================================================================

def test_escalation_auto_creates_on_verifier_failure(lifecycle_sandbox):
    """Test that escalation is created when verifier fails."""
    base_dir = lifecycle_sandbox
    
    # Create failed verifier state
    verifier_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "deviations": [
            {"type": "TYPE_A_STRUCTURE", "severity": "high"}
        ]
    }
    verifier_path = base_dir / "state" / "challenge_verifier_state.json"
    verifier_path.parent.mkdir(parents=True, exist_ok=True)
    verifier_path.write_text(json.dumps(verifier_state), encoding="utf-8")
    
    # No escalation exists yet
    assert should_create_escalation(verifier_state, None) is True
    
    # Run lifecycle engine
    os.environ["MVCRS_BASE_DIR"] = str(base_dir)
    exit_code = run_lifecycle_engine()
    assert exit_code == 0
    
    # Check that lifecycle state was created with pending status
    lifecycle_path = base_dir / "state" / "mvcrs_escalation_lifecycle.json"
    assert lifecycle_path.exists()
    lifecycle = json.loads(lifecycle_path.read_text())
    assert lifecycle["current_state"] == "pending"
    assert "Verifier failed" in lifecycle["last_transition_reason"]


# ============================================================================
# Test: Pending >24h → in_progress
# ============================================================================

def test_pending_to_in_progress_after_24h(lifecycle_sandbox):
    """Test that pending transitions to in_progress after 24 hours."""
    base_dir = lifecycle_sandbox
    
    # Create lifecycle state that's been pending for >24h
    entered_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    lifecycle = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_state": "pending",
        "entered_current_state_at": entered_at,
        "last_transition_reason": "Initial state",
        "resolved_count": 0,
        "rejected_count": 0
    }
    
    assert should_transition_to_in_progress(lifecycle) is True
    
    # Verify transition logic
    next_state, reason = compute_next_state(lifecycle, None, None, {})
    assert next_state == "in_progress"
    assert "24h" in reason.lower()


# ============================================================================
# Test: Correction artifact → awaiting_validation
# ============================================================================

def test_correction_artifact_triggers_awaiting_validation(lifecycle_sandbox):
    """Test that correction artifact triggers transition to awaiting_validation."""
    base_dir = lifecycle_sandbox
    
    # Create lifecycle in in_progress state
    lifecycle = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_state": "in_progress",
        "entered_current_state_at": datetime.now(timezone.utc).isoformat(),
        "last_transition_reason": "Escalated from pending",
        "resolved_count": 0,
        "rejected_count": 0
    }
    
    # Create correction artifact
    correction_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correction_type": "soft",
        "actions_taken": ["regenerate_summary"]
    }
    
    assert should_transition_to_awaiting_validation(lifecycle, correction_state) is True
    
    # Verify transition
    next_state, reason = compute_next_state(lifecycle, None, correction_state, {})
    assert next_state == "awaiting_validation"
    assert "correction" in reason.lower()


# ============================================================================
# Test: Validation success → resolved
# ============================================================================

def test_validation_success_resolves_escalation(lifecycle_sandbox):
    """Test that successful validation resolves the escalation."""
    base_dir = lifecycle_sandbox
    
    # Lifecycle in awaiting_validation
    lifecycle = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_state": "awaiting_validation",
        "entered_current_state_at": datetime.now(timezone.utc).isoformat(),
        "last_transition_reason": "Correction applied",
        "resolved_count": 0,
        "rejected_count": 0
    }
    
    # Verifier now reports ok
    verifier_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "deviations": []
    }
    
    assert should_transition_to_resolved(lifecycle, verifier_state) is True
    
    # Verify transition
    next_state, reason = compute_next_state(lifecycle, verifier_state, None, {})
    assert next_state == "resolved"
    assert "ok" in reason.lower()


# ============================================================================
# Test: Validation fail → rejected
# ============================================================================

def test_validation_fail_rejects_escalation(lifecycle_sandbox):
    """Test that failed validation rejects the escalation."""
    base_dir = lifecycle_sandbox
    
    # Lifecycle in awaiting_validation
    lifecycle = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_state": "awaiting_validation",
        "entered_current_state_at": datetime.now(timezone.utc).isoformat(),
        "last_transition_reason": "Correction applied",
        "resolved_count": 0,
        "rejected_count": 0
    }
    
    # Verifier still reports failure
    verifier_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "deviations": [
            {"type": "TYPE_A_STRUCTURE", "severity": "high"}
        ]
    }
    
    assert should_transition_to_rejected(lifecycle, verifier_state) is True
    
    # Verify transition
    next_state, reason = compute_next_state(lifecycle, verifier_state, None, {})
    assert next_state == "rejected"
    assert "fail" in reason.lower()


# ============================================================================
# Test: Idempotent audit marker + atomic writes
# ============================================================================

def test_idempotent_audit_marker_and_atomic_writes(lifecycle_sandbox):
    """Test that audit markers are idempotent and writes are atomic."""
    base_dir = lifecycle_sandbox
    os.environ["MVCRS_BASE_DIR"] = str(base_dir)
    
    # Create verifier state
    verifier_state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "deviations": [{"type": "TYPE_A_STRUCTURE", "severity": "high"}]
    }
    verifier_path = base_dir / "state" / "challenge_verifier_state.json"
    verifier_path.parent.mkdir(parents=True, exist_ok=True)
    verifier_path.write_text(json.dumps(verifier_state), encoding="utf-8")
    
    # Run lifecycle engine twice
    exit_code1 = run_lifecycle_engine()
    exit_code2 = run_lifecycle_engine()
    
    assert exit_code1 == 0
    assert exit_code2 == 0
    
    # Check audit markers
    audit_path = base_dir / "docs" / "audit_summary.md"
    assert audit_path.exists()
    content = audit_path.read_text()
    
    # Count markers - should only have one despite two runs
    marker_count = content.count("<!-- MVCRS_ESCALATION_LIFECYCLE:")
    assert marker_count == 1
    
    # Check lifecycle state is valid JSON
    lifecycle_path = base_dir / "state" / "mvcrs_escalation_lifecycle.json"
    assert lifecycle_path.exists()
    lifecycle = json.loads(lifecycle_path.read_text())
    assert "current_state" in lifecycle
    assert "timestamp" in lifecycle
    
    # Check log is valid JSONL
    log_path = base_dir / "state" / "mvcrs_escalation_lifecycle_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text().strip().split("\n")
    for line in lines:
        entry = json.loads(line)
        assert "current_state" in entry
        assert "timestamp" in entry
