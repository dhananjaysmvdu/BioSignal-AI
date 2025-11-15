#!/usr/bin/env python3
"""
Regression tests for Policy Fusion Engine

Tests fusion logic:
- RED policy → FUSION_RED
- YELLOW policy + trust unlocked → FUSION_YELLOW
- Weighted consensus < 92% → escalation
- Safety brake active → FUSION_RED
- Atomic write success
- Fix-branch creation on persistent FS failure
- Audit marker insertion (idempotent)
"""

import json
import pytest
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    """Create temporary workspace with mocked paths."""
    state_dir = tmp_path / "state"
    federation_dir = tmp_path / "federation"
    forensics_dir = tmp_path / "forensics"
    audit_file = tmp_path / "audit_summary.md"
    
    state_dir.mkdir()
    federation_dir.mkdir()
    forensics_dir.mkdir()
    audit_file.write_text("# Audit Summary\n")
    
    # Mock module paths
    import sys
    sys.path.insert(0, str(Path("scripts/policy").resolve()))
    import policy_fusion_engine
    
    monkeypatch.setattr(policy_fusion_engine, "STATE_DIR", state_dir)
    monkeypatch.setattr(policy_fusion_engine, "FEDERATION_DIR", federation_dir)
    monkeypatch.setattr(policy_fusion_engine, "FORENSICS_DIR", forensics_dir)
    monkeypatch.setattr(policy_fusion_engine, "AUDIT_FILE", audit_file)
    
    monkeypatch.setattr(policy_fusion_engine, "POLICY_STATE", state_dir / "policy_state.json")
    monkeypatch.setattr(policy_fusion_engine, "TRUST_LOCK_STATE", tmp_path / "trust_lock_state.json")
    monkeypatch.setattr(policy_fusion_engine, "RESPONSE_LOG", state_dir / "policy_response_log.jsonl")
    monkeypatch.setattr(policy_fusion_engine, "ADAPTIVE_RESPONSE_HISTORY", state_dir / "adaptive_response_history.jsonl")
    monkeypatch.setattr(policy_fusion_engine, "WEIGHTED_CONSENSUS", federation_dir / "weighted_consensus.json")
    monkeypatch.setattr(policy_fusion_engine, "SAFETY_BRAKE_STATE", forensics_dir / "safety_brake_state.json")
    monkeypatch.setattr(policy_fusion_engine, "FUSION_STATE", state_dir / "policy_fusion_state.json")
    monkeypatch.setattr(policy_fusion_engine, "FUSION_LOG", state_dir / "policy_fusion_log.jsonl")
    
    paths = {
        "state_dir": state_dir,
        "federation_dir": federation_dir,
        "forensics_dir": forensics_dir,
        "audit_file": audit_file,
        "policy_state": state_dir / "policy_state.json",
        "trust_lock_state": tmp_path / "trust_lock_state.json",
        "weighted_consensus": federation_dir / "weighted_consensus.json",
        "safety_brake_state": forensics_dir / "safety_brake_state.json",
        "fusion_state": state_dir / "policy_fusion_state.json",
        "fusion_log": state_dir / "policy_fusion_log.jsonl"
    }
    
    return paths


def test_fusion_red_from_policy_red(temp_workspace):
    """Test: RED policy → FUSION_RED"""
    # Setup: RED policy
    temp_workspace["policy_state"].write_text(json.dumps({
        "policy": "RED",
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }))
    temp_workspace["trust_lock_state"].write_text(json.dumps({"locked": False}))
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}))
    temp_workspace["safety_brake_state"].write_text(json.dumps({"is_engaged": False}))
    
    # Execute
    from policy_fusion_engine import compute_fusion_status
    fusion = compute_fusion_status()
    
    # Verify
    assert fusion["fusion_level"] == "FUSION_RED"
    assert "policy_red" in fusion["reasons"]


def test_fusion_yellow_from_policy_yellow_trust_unlocked(temp_workspace):
    """Test: YELLOW policy + trust unlocked → FUSION_YELLOW"""
    # Setup: YELLOW policy, trust unlocked
    temp_workspace["policy_state"].write_text(json.dumps({
        "policy": "YELLOW",
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }))
    temp_workspace["trust_lock_state"].write_text(json.dumps({"locked": False}))
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}))
    temp_workspace["safety_brake_state"].write_text(json.dumps({"is_engaged": False}))
    
    # Execute
    from policy_fusion_engine import compute_fusion_status
    fusion = compute_fusion_status()
    
    # Verify
    assert fusion["fusion_level"] == "FUSION_YELLOW"
    assert "policy_yellow_trust_unlocked" in fusion["reasons"]


def test_fusion_escalation_from_low_consensus(temp_workspace):
    """Test: Weighted consensus < 92% → escalation"""
    # Setup: GREEN policy, low consensus
    temp_workspace["policy_state"].write_text(json.dumps({
        "policy": "GREEN",
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }))
    temp_workspace["trust_lock_state"].write_text(json.dumps({"locked": False}))
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 85.0}))
    temp_workspace["safety_brake_state"].write_text(json.dumps({"is_engaged": False}))
    
    # Execute
    from policy_fusion_engine import compute_fusion_status
    fusion = compute_fusion_status()
    
    # Verify: GREEN + low consensus → YELLOW escalation
    assert fusion["fusion_level"] == "FUSION_YELLOW"
    assert any("consensus_low" in r for r in fusion["reasons"])
    assert fusion["inputs"]["weighted_consensus_pct"] == 85.0


def test_fusion_red_from_safety_brake(temp_workspace):
    """Test: Safety brake active → FUSION_RED"""
    # Setup: GREEN policy, but safety brake engaged
    temp_workspace["policy_state"].write_text(json.dumps({
        "policy": "GREEN",
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }))
    temp_workspace["trust_lock_state"].write_text(json.dumps({"locked": False}))
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}))
    temp_workspace["safety_brake_state"].write_text(json.dumps({"is_engaged": True}))
    
    # Execute
    from policy_fusion_engine import compute_fusion_status
    fusion = compute_fusion_status()
    
    # Verify
    assert fusion["fusion_level"] == "FUSION_RED"
    assert "safety_brake_engaged" in fusion["reasons"]


def test_atomic_write_success(temp_workspace):
    """Test: Atomic write creates fusion state file"""
    # Setup
    temp_workspace["policy_state"].write_text(json.dumps({
        "policy": "GREEN",
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }))
    temp_workspace["trust_lock_state"].write_text(json.dumps({"locked": False}))
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}))
    temp_workspace["safety_brake_state"].write_text(json.dumps({"is_engaged": False}))
    
    # Execute
    from policy_fusion_engine import run_fusion_engine
    result = run_fusion_engine()
    
    # Verify
    assert result == 0
    assert temp_workspace["fusion_state"].exists()
    fusion_data = json.loads(temp_workspace["fusion_state"].read_text())
    assert fusion_data["fusion_level"] == "FUSION_GREEN"
    assert "computed_at" in fusion_data


def test_fix_branch_on_persistent_fs_failure(temp_workspace, monkeypatch):
    """Test: Fix-branch creation on persistent FS failure"""
    # Setup
    temp_workspace["policy_state"].write_text(json.dumps({
        "policy": "GREEN",
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }))
    temp_workspace["trust_lock_state"].write_text(json.dumps({"locked": False}))
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}))
    temp_workspace["safety_brake_state"].write_text(json.dumps({"is_engaged": False}))
    
    # Mock atomic_write_json to fail persistently
    from policy_fusion_engine import atomic_write_json
    
    def mock_atomic_write(*args, **kwargs):
        raise IOError("Mocked persistent FS failure")
    
    monkeypatch.setattr("policy_fusion_engine.atomic_write_json", mock_atomic_write)
    
    # Mock subprocess.run to track git commands
    git_commands = []
    
    def mock_subprocess_run(cmd, *args, **kwargs):
        git_commands.append(cmd)
        return MagicMock(returncode=0)
    
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
    
    # Execute
    from policy_fusion_engine import run_fusion_engine
    result = run_fusion_engine()
    
    # Verify: Should fail and create fix branch
    assert result == 1
    assert any("git" in str(cmd) and "checkout" in str(cmd) and "fix/policy-fusion" in str(cmd) for cmd in git_commands)


def test_audit_marker_idempotent(temp_workspace):
    """Test: Audit marker insertion is idempotent"""
    # Setup
    temp_workspace["policy_state"].write_text(json.dumps({
        "policy": "GREEN",
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }))
    temp_workspace["trust_lock_state"].write_text(json.dumps({"locked": False}))
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}))
    temp_workspace["safety_brake_state"].write_text(json.dumps({"is_engaged": False}))
    
    # Execute twice
    from policy_fusion_engine import run_fusion_engine
    run_fusion_engine()
    run_fusion_engine()
    
    # Verify: Only one fusion marker should exist
    audit_content = temp_workspace["audit_file"].read_text()
    fusion_markers = [line for line in audit_content.splitlines() if "POLICY_FUSION: UPDATED" in line]
    assert len(fusion_markers) == 1


def test_yellow_escalates_to_red_with_low_consensus(temp_workspace):
    """Test: YELLOW + low consensus → FUSION_RED"""
    # Setup: YELLOW policy, low consensus
    temp_workspace["policy_state"].write_text(json.dumps({
        "policy": "YELLOW",
        "evaluated_at": datetime.now(timezone.utc).isoformat()
    }))
    temp_workspace["trust_lock_state"].write_text(json.dumps({"locked": False}))
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 85.0}))
    temp_workspace["safety_brake_state"].write_text(json.dumps({"is_engaged": False}))
    
    # Execute
    from policy_fusion_engine import compute_fusion_status
    fusion = compute_fusion_status()
    
    # Verify: YELLOW + low consensus → escalate to RED
    assert fusion["fusion_level"] == "FUSION_RED"
    assert "policy_yellow_trust_unlocked" in fusion["reasons"]
    assert any("consensus_low" in r for r in fusion["reasons"])
