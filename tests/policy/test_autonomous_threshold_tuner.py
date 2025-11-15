#!/usr/bin/env python3
"""
Regression tests for Autonomous Threshold Tuning Engine (ATTE)

Test matrix:
- Rising anomalies → thresholds rise
- Improving metrics → thresholds relax slightly
- Stability < 0.85 → thresholds locked
- 21-day data window adhered to
- Safety clamps respected (no illegal values)
- Fix-branch creation on FS failure
- Audit marker insertion (idempotent)
- JSON structure valid and complete
"""

import json
import pytest
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    """Create temporary workspace with mocked paths."""
    exports_dir = tmp_path / "exports"
    federation_dir = tmp_path / "federation"
    forensics_dir = tmp_path / "forensics" / "forecast"
    state_dir = tmp_path / "state"
    audit_file = tmp_path / "audit_summary.md"
    
    exports_dir.mkdir(parents=True)
    federation_dir.mkdir(parents=True)
    forensics_dir.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    audit_file.write_text("# Audit Summary\n", encoding="utf-8")
    
    # Mock module paths
    import sys
    sys.path.insert(0, str(Path("scripts/policy").resolve()))
    import autonomous_threshold_tuner
    
    monkeypatch.setattr(autonomous_threshold_tuner, "EXPORTS_DIR", exports_dir)
    monkeypatch.setattr(autonomous_threshold_tuner, "FEDERATION_DIR", federation_dir)
    monkeypatch.setattr(autonomous_threshold_tuner, "FORENSICS_DIR", tmp_path / "forensics")
    monkeypatch.setattr(autonomous_threshold_tuner, "STATE_DIR", state_dir)
    monkeypatch.setattr(autonomous_threshold_tuner, "AUDIT_FILE", audit_file)
    
    monkeypatch.setattr(autonomous_threshold_tuner, "INTEGRITY_REGISTRY", exports_dir / "integrity_metrics_registry.csv")
    monkeypatch.setattr(autonomous_threshold_tuner, "WEIGHTED_CONSENSUS", federation_dir / "weighted_consensus.json")
    monkeypatch.setattr(autonomous_threshold_tuner, "REPUTATION_INDEX", federation_dir / "reputation_index.json")
    monkeypatch.setattr(autonomous_threshold_tuner, "FORECAST_FILE", forensics_dir / "forensic_forecast.json")
    monkeypatch.setattr(autonomous_threshold_tuner, "THRESHOLD_POLICY", state_dir / "threshold_policy.json")
    monkeypatch.setattr(autonomous_threshold_tuner, "THRESHOLD_HISTORY", state_dir / "threshold_tuning_history.jsonl")
    
    paths = {
        "exports_dir": exports_dir,
        "federation_dir": federation_dir,
        "forensics_dir": forensics_dir,
        "state_dir": state_dir,
        "audit_file": audit_file,
        "integrity_registry": exports_dir / "integrity_metrics_registry.csv",
        "weighted_consensus": federation_dir / "weighted_consensus.json",
        "reputation_index": federation_dir / "reputation_index.json",
        "forecast_file": forensics_dir / "forensic_forecast.json",
        "threshold_policy": state_dir / "threshold_policy.json",
        "threshold_history": state_dir / "threshold_tuning_history.jsonl"
    }
    
    return paths


def test_rising_anomalies_increase_thresholds(temp_workspace):
    """Test: Rising anomalies → thresholds rise"""
    # Setup: Declining integrity scores (simulating anomalies)
    integrity_data = "timestamp,component,metric,value\n"
    base_time = datetime.now(timezone.utc)
    for i in range(21):
        score = 95.0 - (i * 0.5)  # Declining trend
        timestamp = (base_time - timedelta(days=20-i)).isoformat()
        integrity_data += f"{timestamp},test,integrity,{score}\n"
    
    temp_workspace["integrity_registry"].write_text(integrity_data, encoding="utf-8")
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}), encoding="utf-8")
    temp_workspace["reputation_index"].write_text(json.dumps({"average_reputation": 90.0}), encoding="utf-8")
    temp_workspace["forecast_file"].write_text(json.dumps({"forecast_risk": "low"}), encoding="utf-8")
    
    # Set initial thresholds
    initial = {
        "integrity": {"green": 90.0, "yellow": 85.0},
        "consensus": {"green": 95.0, "yellow": 90.0},
        "forecast": {"low": 5, "medium": 15, "high": 30},
        "responses": {"soft": 7, "hard": 10},
        "reputation": {"min_peer_score": 70.0},
        "status": "stable"
    }
    temp_workspace["threshold_policy"].write_text(json.dumps(initial), encoding="utf-8")
    
    # Execute
    from autonomous_threshold_tuner import run_threshold_tuner
    result = run_threshold_tuner(dry_run=False)
    
    # Verify: Thresholds should rise due to declining quality
    assert result == 0
    with temp_workspace["threshold_policy"].open("r", encoding="utf-8") as f:
        updated = json.load(f)
    
    # Integrity thresholds should increase (tightened)
    assert updated["integrity"]["green"] >= initial["integrity"]["green"]


def test_improving_metrics_relax_thresholds(temp_workspace):
    """Test: Improving metrics → thresholds relax slightly"""
    from datetime import timedelta
    
    # Setup: Improving integrity scores
    integrity_data = "timestamp,component,metric,value\n"
    base_time = datetime.now(timezone.utc)
    for i in range(21):
        score = 85.0 + (i * 0.5)  # Improving trend
        timestamp = (base_time - timedelta(days=20-i)).isoformat()
        integrity_data += f"{timestamp},test,integrity,{score}\n"
    
    temp_workspace["integrity_registry"].write_text(integrity_data, encoding="utf-8")
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 98.0}), encoding="utf-8")
    temp_workspace["reputation_index"].write_text(json.dumps({"average_reputation": 95.0}), encoding="utf-8")
    temp_workspace["forecast_file"].write_text(json.dumps({"forecast_risk": "low"}), encoding="utf-8")
    
    # Set initial thresholds
    initial = {
        "integrity": {"green": 92.0, "yellow": 87.0},
        "consensus": {"green": 95.0, "yellow": 90.0},
        "forecast": {"low": 5, "medium": 15, "high": 30},
        "responses": {"soft": 7, "hard": 10},
        "reputation": {"min_peer_score": 70.0},
        "status": "stable"
    }
    temp_workspace["threshold_policy"].write_text(json.dumps(initial), encoding="utf-8")
    
    # Execute
    from autonomous_threshold_tuner import run_threshold_tuner
    result = run_threshold_tuner(dry_run=False)
    
    # Verify: Thresholds should relax due to improving quality
    assert result == 0
    with temp_workspace["threshold_policy"].open("r", encoding="utf-8") as f:
        updated = json.load(f)
    
    # Integrity thresholds should decrease (relaxed) or stay same
    assert updated["integrity"]["green"] <= initial["integrity"]["green"]


def test_low_stability_locks_thresholds(temp_workspace):
    """Test: Stability < 0.85 → thresholds locked"""
    # Setup: Create fusion log with high flip rate (low stability)
    fusion_log = temp_workspace["state_dir"] / "policy_fusion_log.jsonl"
    base_time = datetime.now(timezone.utc)
    
    # Create alternating fusion levels (high flip rate)
    from datetime import timedelta
    for i in range(20):
        level = "FUSION_RED" if i % 2 == 0 else "FUSION_GREEN"
        record = {
            "fusion_level": level,
            "timestamp": (base_time - timedelta(days=19-i)).isoformat(),
            "inputs": {"weighted_consensus_pct": 95.0}
        }
        with fusion_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}), encoding="utf-8")
    temp_workspace["reputation_index"].write_text(json.dumps({"average_reputation": 90.0}), encoding="utf-8")
    temp_workspace["forecast_file"].write_text(json.dumps({"forecast_risk": "low"}), encoding="utf-8")
    
    # Set initial thresholds
    initial = {
        "integrity": {"green": 90.0, "yellow": 85.0},
        "consensus": {"green": 95.0, "yellow": 90.0},
        "forecast": {"low": 5, "medium": 15, "high": 30},
        "responses": {"soft": 7, "hard": 10},
        "reputation": {"min_peer_score": 70.0},
        "status": "stable"
    }
    temp_workspace["threshold_policy"].write_text(json.dumps(initial), encoding="utf-8")
    
    # Execute
    from autonomous_threshold_tuner import run_threshold_tuner
    result = run_threshold_tuner(dry_run=False)
    
    # Verify: Status should be "locked"
    assert result == 0
    with temp_workspace["threshold_policy"].open("r", encoding="utf-8") as f:
        updated = json.load(f)
    
    assert updated["status"] == "locked"
    assert "stability" in updated.get("reason", "")


def test_safety_clamps_respected(temp_workspace):
    """Test: Safety clamps respected (no illegal values)"""
    # Setup: Extremely low integrity scores to test safety clamps
    integrity_data = "timestamp,component,metric,value\n"
    base_time = datetime.now(timezone.utc)
    from datetime import timedelta
    for i in range(21):
        score = 80.0  # Below minimum
        timestamp = (base_time - timedelta(days=20-i)).isoformat()
        integrity_data += f"{timestamp},test,integrity,{score}\n"
    
    temp_workspace["integrity_registry"].write_text(integrity_data, encoding="utf-8")
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 88.0}), encoding="utf-8")
    temp_workspace["reputation_index"].write_text(json.dumps({"average_reputation": 40.0}), encoding="utf-8")
    temp_workspace["forecast_file"].write_text(json.dumps({"forecast_risk": "low"}), encoding="utf-8")
    
    # Set initial thresholds at minimum
    initial = {
        "integrity": {"green": 85.0, "yellow": 85.0},
        "consensus": {"green": 90.0, "yellow": 90.0},
        "forecast": {"low": 5, "medium": 15, "high": 30},
        "responses": {"soft": 7, "hard": 10},
        "reputation": {"min_peer_score": 50.0},
        "status": "stable"
    }
    temp_workspace["threshold_policy"].write_text(json.dumps(initial), encoding="utf-8")
    
    # Execute
    from autonomous_threshold_tuner import run_threshold_tuner
    result = run_threshold_tuner(dry_run=False)
    
    # Verify: Safety clamps enforced
    assert result == 0
    with temp_workspace["threshold_policy"].open("r", encoding="utf-8") as f:
        updated = json.load(f)
    
    # Integrity thresholds must be >= 85
    assert updated["integrity"]["green"] >= 85.0
    assert updated["integrity"]["yellow"] >= 85.0
    
    # Consensus thresholds must be >= 90
    assert updated["consensus"]["green"] >= 90.0
    assert updated["consensus"]["yellow"] >= 90.0
    
    # Reputation must be >= 50
    assert updated["reputation"]["min_peer_score"] >= 50.0


def test_fix_branch_creation_on_fs_failure(temp_workspace, monkeypatch):
    """Test: Fix-branch creation on FS failure"""
    # Setup basic data
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}), encoding="utf-8")
    temp_workspace["reputation_index"].write_text(json.dumps({"average_reputation": 90.0}), encoding="utf-8")
    temp_workspace["forecast_file"].write_text(json.dumps({"forecast_risk": "low"}), encoding="utf-8")
    
    # Mock atomic_write_json to fail
    def mock_atomic_write(*args, **kwargs):
        raise IOError("Mocked persistent FS failure")
    
    monkeypatch.setattr("autonomous_threshold_tuner.atomic_write_json", mock_atomic_write)
    
    # Mock subprocess.run to track git commands
    git_commands = []
    
    def mock_subprocess_run(cmd, *args, **kwargs):
        git_commands.append(cmd)
        return MagicMock(returncode=0)
    
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)
    
    # Execute
    from autonomous_threshold_tuner import run_threshold_tuner
    result = run_threshold_tuner(dry_run=False)
    
    # Verify: Should fail and create fix branch
    assert result == 1
    assert any("git" in str(cmd) and "checkout" in str(cmd) and "fix/threshold-tuner" in str(cmd) for cmd in git_commands)


def test_audit_marker_idempotent(temp_workspace):
    """Test: Audit marker insertion is idempotent"""
    # Setup basic data
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}), encoding="utf-8")
    temp_workspace["reputation_index"].write_text(json.dumps({"average_reputation": 90.0}), encoding="utf-8")
    temp_workspace["forecast_file"].write_text(json.dumps({"forecast_risk": "low"}), encoding="utf-8")
    
    initial = {
        "integrity": {"green": 90.0, "yellow": 85.0},
        "consensus": {"green": 95.0, "yellow": 90.0},
        "forecast": {"low": 5, "medium": 15, "high": 30},
        "responses": {"soft": 7, "hard": 10},
        "reputation": {"min_peer_score": 70.0},
        "status": "stable"
    }
    temp_workspace["threshold_policy"].write_text(json.dumps(initial), encoding="utf-8")
    
    # Execute twice
    from autonomous_threshold_tuner import run_threshold_tuner
    run_threshold_tuner(dry_run=False)
    run_threshold_tuner(dry_run=False)
    
    # Verify: Only one ATTE marker should exist
    audit_content = temp_workspace["audit_file"].read_text(encoding="utf-8")
    atte_markers = [line for line in audit_content.splitlines() if "ATTE: UPDATED" in line]
    assert len(atte_markers) == 1


def test_json_structure_valid(temp_workspace):
    """Test: JSON structure valid and complete"""
    # Setup basic data
    temp_workspace["weighted_consensus"].write_text(json.dumps({"weighted_consensus_pct": 95.0}), encoding="utf-8")
    temp_workspace["reputation_index"].write_text(json.dumps({"average_reputation": 90.0}), encoding="utf-8")
    temp_workspace["forecast_file"].write_text(json.dumps({"forecast_risk": "low"}), encoding="utf-8")
    
    # Execute
    from autonomous_threshold_tuner import run_threshold_tuner
    result = run_threshold_tuner(dry_run=False)
    
    # Verify: JSON structure complete
    assert result == 0
    with temp_workspace["threshold_policy"].open("r", encoding="utf-8") as f:
        policy = json.load(f)
    
    # Required fields
    assert "integrity" in policy
    assert "green" in policy["integrity"]
    assert "yellow" in policy["integrity"]
    
    assert "consensus" in policy
    assert "green" in policy["consensus"]
    assert "yellow" in policy["consensus"]
    
    assert "forecast" in policy
    assert "low" in policy["forecast"]
    assert "medium" in policy["forecast"]
    assert "high" in policy["forecast"]
    
    assert "responses" in policy
    assert "soft" in policy["responses"]
    assert "hard" in policy["responses"]
    
    assert "reputation" in policy
    assert "min_peer_score" in policy["reputation"]
    
    assert "status" in policy
    assert "last_updated" in policy
