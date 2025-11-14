#!/usr/bin/env python3
"""
Regression tests for Policy Orchestrator Engine.
Tests GREEN/YELLOW/RED policy paths, log append structure, atomic writes, and fix-branch creation.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace with mocked input files."""
    # Create directory structure
    (tmp_path / 'trust_lock_state.json').write_text('{"locked": false}')
    (tmp_path / 'exports').mkdir()
    (tmp_path / 'exports' / 'integrity_metrics_registry.csv').write_text(
        'timestamp,integrity_score\n2025-11-14T00:00:00+00:00,97.5\n'
    )
    (tmp_path / 'federation').mkdir()
    (tmp_path / 'federation' / 'weighted_consensus.json').write_text('{"weighted_agreement_pct": 95.0}')
    (tmp_path / 'federation' / 'reputation_index.json').write_text('{"peers": [{"reputation_score": 85.0}]}')
    (tmp_path / 'forensics').mkdir()
    (tmp_path / 'forensics' / 'forensics_anomaly_forecast.json').write_text('{"risk_level": "low"}')
    (tmp_path / 'forensics' / 'response_history.jsonl').write_text(
        '{"timestamp":"2025-11-14T00:00:00+00:00","actions_taken":[]}\n'
    )
    (tmp_path / 'state').mkdir()
    (tmp_path / 'audit_summary.md').write_text('# Audit Summary\n\n')
    
    return tmp_path


def test_green_path(temp_workspace, monkeypatch):
    """Test GREEN policy path with all signals healthy."""
    monkeypatch.chdir(temp_workspace)
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'policy'))
    from policy_orchestrator import compute_policy
    
    policy = compute_policy(
        trust_locked=False,
        integrity_score=97.5,
        consensus_pct=95.0,
        reputation_score=85.0,
        forecast_risk='low',
        recent_responses=2
    )
    
    assert policy == 'GREEN'


def test_yellow_path_moderate_risk(temp_workspace, monkeypatch):
    """Test YELLOW policy path with moderate risk signals."""
    monkeypatch.chdir(temp_workspace)
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'policy'))
    from policy_orchestrator import compute_policy
    
    # Integrity at 92% (below 95% threshold)
    policy = compute_policy(
        trust_locked=False,
        integrity_score=92.0,
        consensus_pct=95.0,
        reputation_score=85.0,
        forecast_risk='low',
        recent_responses=2
    )
    assert policy == 'YELLOW'
    
    # Consensus at 88% (below 90% threshold)
    policy = compute_policy(
        trust_locked=False,
        integrity_score=97.5,
        consensus_pct=88.0,
        reputation_score=85.0,
        forecast_risk='low',
        recent_responses=2
    )
    assert policy == 'YELLOW'
    
    # Medium forecast risk
    policy = compute_policy(
        trust_locked=False,
        integrity_score=97.5,
        consensus_pct=95.0,
        reputation_score=85.0,
        forecast_risk='medium',
        recent_responses=2
    )
    assert policy == 'YELLOW'
    
    # 5 recent responses (between 4-7)
    policy = compute_policy(
        trust_locked=False,
        integrity_score=97.5,
        consensus_pct=95.0,
        reputation_score=85.0,
        forecast_risk='low',
        recent_responses=5
    )
    assert policy == 'YELLOW'


def test_red_path_critical_conditions(temp_workspace, monkeypatch):
    """Test RED policy path with critical conditions."""
    monkeypatch.chdir(temp_workspace)
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'policy'))
    from policy_orchestrator import compute_policy
    
    # Trust guard locked
    policy = compute_policy(
        trust_locked=True,
        integrity_score=97.5,
        consensus_pct=95.0,
        reputation_score=85.0,
        forecast_risk='low',
        recent_responses=2
    )
    assert policy == 'RED'
    
    # Integrity < 90%
    policy = compute_policy(
        trust_locked=False,
        integrity_score=85.0,
        consensus_pct=95.0,
        reputation_score=85.0,
        forecast_risk='low',
        recent_responses=2
    )
    assert policy == 'RED'
    
    # Consensus < 85%
    policy = compute_policy(
        trust_locked=False,
        integrity_score=97.5,
        consensus_pct=80.0,
        reputation_score=85.0,
        forecast_risk='low',
        recent_responses=2
    )
    assert policy == 'RED'
    
    # High forecast risk
    policy = compute_policy(
        trust_locked=False,
        integrity_score=97.5,
        consensus_pct=95.0,
        reputation_score=85.0,
        forecast_risk='high',
        recent_responses=2
    )
    assert policy == 'RED'
    
    # Many recent responses (>= 8)
    policy = compute_policy(
        trust_locked=False,
        integrity_score=97.5,
        consensus_pct=95.0,
        reputation_score=85.0,
        forecast_risk='low',
        recent_responses=10
    )
    assert policy == 'RED'


def test_log_append_structure(temp_workspace, monkeypatch):
    """Test JSONL log append structure."""
    monkeypatch.chdir(temp_workspace)
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'policy'))
    from policy_orchestrator import run_orchestrator
    
    result = run_orchestrator()
    assert result == 0
    
    log_path = temp_workspace / 'state' / 'policy_state_log.jsonl'
    assert log_path.exists()
    
    with open(log_path, 'r') as f:
        line = f.readline().strip()
        entry = json.loads(line)
        
        # Verify required fields
        assert 'timestamp' in entry
        assert 'policy' in entry
        assert 'trust_locked' in entry
        assert 'integrity' in entry
        assert 'consensus' in entry
        assert 'reputation' in entry
        assert 'forecast' in entry
        assert 'responses' in entry
        
        # Verify ISO 8601 timestamp
        datetime.fromisoformat(entry['timestamp'])


def test_atomic_write_paths(temp_workspace, monkeypatch):
    """Test atomic write functionality."""
    monkeypatch.chdir(temp_workspace)
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'policy'))
    from policy_orchestrator import run_orchestrator
    
    result = run_orchestrator()
    assert result == 0
    
    state_path = temp_workspace / 'state' / 'policy_state.json'
    assert state_path.exists()
    
    # Verify no .tmp files left behind
    tmp_files = list(temp_workspace.glob('**/*.tmp'))
    assert len(tmp_files) == 0
    
    # Verify valid JSON
    with open(state_path, 'r') as f:
        state = json.load(f)
        assert 'policy' in state
        assert 'evaluated_at' in state
        assert 'inputs' in state
        assert 'thresholds' in state


def test_audit_marker_idempotent(temp_workspace, monkeypatch):
    """Test that audit markers are idempotent (replace, not duplicate)."""
    monkeypatch.chdir(temp_workspace)
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'policy'))
    from policy_orchestrator import run_orchestrator
    
    # Run twice
    run_orchestrator()
    run_orchestrator()
    
    audit_path = temp_workspace / 'audit_summary.md'
    content = audit_path.read_text()
    
    # Count markers - should only be one
    marker_count = content.count('<!-- POLICY_ORCHESTRATION:')
    assert marker_count == 1


def test_fix_branch_logic():
    """Test fix-branch creation logic in isolation."""
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'policy'))
    from policy_orchestrator import create_fix_branch
    
    with patch('subprocess.run') as mock_run:
        create_fix_branch("test error")
        
        # Verify git command was called
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert 'git' in args
        assert 'checkout' in args
        assert '-b' in args
        assert any('fix/policy-orchestrator-' in arg for arg in args)


def test_full_integration_run(temp_workspace, monkeypatch):
    """Full integration test with realistic inputs."""
    monkeypatch.chdir(temp_workspace)
    
    # Update inputs to trigger YELLOW policy
    (temp_workspace / 'exports' / 'integrity_metrics_registry.csv').write_text(
        'timestamp,integrity_score\n2025-11-14T00:00:00+00:00,92.0\n'
    )
    (temp_workspace / 'forensics' / 'forensics_anomaly_forecast.json').write_text(
        '{"risk_level": "medium"}'
    )
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'policy'))
    from policy_orchestrator import run_orchestrator
    
    result = run_orchestrator()
    assert result == 0
    
    # Verify state file
    state_path = temp_workspace / 'state' / 'policy_state.json'
    with open(state_path, 'r') as f:
        state = json.load(f)
        assert state['policy'] == 'YELLOW'
        assert state['inputs']['integrity_score'] == 92.0
        assert state['inputs']['forecast_risk'] == 'medium'
    
    # Verify log entry
    log_path = temp_workspace / 'state' / 'policy_state_log.jsonl'
    with open(log_path, 'r') as f:
        entry = json.loads(f.readline())
        assert entry['policy'] == 'YELLOW'
        assert entry['integrity'] == 92.0
        assert entry['forecast'] == 'medium'
    
    # Verify audit marker
    audit_path = temp_workspace / 'audit_summary.md'
    content = audit_path.read_text()
    assert '<!-- POLICY_ORCHESTRATION: UPDATED' in content
    assert 'policy=YELLOW' in content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
