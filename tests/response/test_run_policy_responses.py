#!/usr/bin/env python3
"""
Regression tests for Policy Response Runner.
Tests dry-run, apply modes, safety gates, and undo file creation.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace with mocked state files."""
    # Trust guard unlocked
    (tmp_path / 'trust_lock_state.json').write_text('{"locked": false, "manual_unlocks_today": 0}')
    
    # Safety brake OFF
    (tmp_path / 'forensics').mkdir()
    (tmp_path / 'forensics' / 'safety_brake_state.json').write_text(
        '{"is_engaged": false, "response_count_24h": 2, "max_allowed": 10}'
    )
    
    # Policy
    (tmp_path / 'policy').mkdir()
    (tmp_path / 'policy' / 'trust_guard_policy.json').write_text(
        '{"manual_unlock_daily_limit": 3}'
    )
    
    # Create state and reports dirs
    (tmp_path / 'state').mkdir()
    (tmp_path / 'reports').mkdir()
    (tmp_path / 'audit_summary.md').write_text('# Audit Summary\n\n')
    
    return tmp_path


def test_dry_run_yellow_policy(temp_workspace, monkeypatch):
    """Test dry-run mode with YELLOW policy."""
    monkeypatch.chdir(temp_workspace)
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'response'))
    from run_policy_responses import run_response
    
    result = run_response('YELLOW', apply=False)
    assert result == 0
    
    # Verify preview file created
    preview_path = temp_workspace / 'state' / 'policy_response_preview.json'
    assert preview_path.exists()
    
    with open(preview_path, 'r') as f:
        preview = json.load(f)
        assert preview['mode'] == 'dry-run'
        assert preview['policy'] == 'YELLOW'
        assert preview['actions_planned'] == 2
        assert all('[DRY-RUN]' in r['stdout'] for r in preview['results'])


def test_trust_lock_blocks_execution(temp_workspace, monkeypatch):
    """Test that trust guard lock blocks execution."""
    monkeypatch.chdir(temp_workspace)
    
    # Lock trust guard
    (temp_workspace / 'trust_lock_state.json').write_text('{"locked": true}')
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'response'))
    from run_policy_responses import run_response
    
    result = run_response('RED', apply=True)
    assert result == 1  # Blocked
    
    # Verify blocked report
    blocked_path = temp_workspace / 'reports' / 'policy_response_blocked.json'
    assert blocked_path.exists()
    
    with open(blocked_path, 'r') as f:
        blocked = json.load(f)
        assert blocked['blocked'] is True
        assert blocked['reason'] == 'trust_guard_locked'


def test_safety_brake_blocks_execution(temp_workspace, monkeypatch):
    """Test that engaged safety brake blocks execution."""
    monkeypatch.chdir(temp_workspace)
    
    # Engage safety brake
    (temp_workspace / 'forensics' / 'safety_brake_state.json').write_text(
        '{"is_engaged": true, "response_count_24h": 10, "max_allowed": 10}'
    )
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'response'))
    from run_policy_responses import run_response
    
    result = run_response('RED', apply=True)
    assert result == 1  # Blocked
    
    # Verify blocked report
    blocked_path = temp_workspace / 'reports' / 'policy_response_blocked.json'
    assert blocked_path.exists()
    
    with open(blocked_path, 'r') as f:
        blocked = json.load(f)
        assert 'safety_brake' in blocked['reason']


def test_rate_limit_blocks_execution(temp_workspace, monkeypatch):
    """Test that rate limit blocks execution."""
    monkeypatch.chdir(temp_workspace)
    
    # Hit rate limit
    (temp_workspace / 'forensics' / 'safety_brake_state.json').write_text(
        '{"is_engaged": false, "response_count_24h": 10, "max_allowed": 10}'
    )
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'response'))
    from run_policy_responses import run_response
    
    result = run_response('RED', apply=True)
    assert result == 1  # Blocked
    
    blocked_path = temp_workspace / 'reports' / 'policy_response_blocked.json'
    assert blocked_path.exists()
    
    with open(blocked_path, 'r') as f:
        blocked = json.load(f)
        assert 'rate_limit' in blocked['reason']


@patch('subprocess.run')
def test_apply_mode_executes_actions(mock_run, temp_workspace, monkeypatch):
    """Test apply mode executes real actions."""
    monkeypatch.chdir(temp_workspace)
    
    # Mock subprocess success
    mock_run.return_value = MagicMock(returncode=0, stdout='Success', stderr='')
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'response'))
    from run_policy_responses import run_response
    
    result = run_response('YELLOW', apply=True)
    assert result == 0
    
    # Verify log file created
    log_path = temp_workspace / 'state' / 'policy_response_log.jsonl'
    assert log_path.exists()
    
    with open(log_path, 'r') as f:
        log_entry = json.loads(f.readline())
        assert log_entry['mode'] == 'apply'
        assert log_entry['policy'] == 'YELLOW'
    
    # Verify subprocess called
    assert mock_run.called


@patch('subprocess.run')
def test_undo_file_created_for_reversible_actions(mock_run, temp_workspace, monkeypatch):
    """Test that undo files are created for reversible actions."""
    monkeypatch.chdir(temp_workspace)
    
    mock_run.return_value = MagicMock(returncode=0, stdout='Success', stderr='')
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'response'))
    from run_policy_responses import run_response
    
    result = run_response('RED', apply=True)
    assert result == 0
    
    # Check for undo files (RED policy has reversible actions)
    undo_files = list(temp_workspace.glob('state/policy_response_undo_*.json'))
    assert len(undo_files) > 0
    
    # Verify undo file structure
    with open(undo_files[0], 'r') as f:
        undo_data = json.load(f)
        assert 'response_id' in undo_data
        assert 'action' in undo_data
        assert 'undo_instruction' in undo_data


def test_green_policy_no_actions(temp_workspace, monkeypatch):
    """Test GREEN policy executes no actions."""
    monkeypatch.chdir(temp_workspace)
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'response'))
    from run_policy_responses import run_response
    
    result = run_response('GREEN', apply=True)
    assert result == 0
    
    # Verify no preview or log files created
    assert not (temp_workspace / 'state' / 'policy_response_preview.json').exists()
    assert not (temp_workspace / 'state' / 'policy_response_log.jsonl').exists()


def test_audit_marker_on_blocked(temp_workspace, monkeypatch):
    """Test audit marker appended when blocked."""
    monkeypatch.chdir(temp_workspace)
    
    # Lock trust guard
    (temp_workspace / 'trust_lock_state.json').write_text('{"locked": true}')
    
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'response'))
    from run_policy_responses import run_response
    
    run_response('RED', apply=True)
    
    audit_path = temp_workspace / 'audit_summary.md'
    content = audit_path.read_text()
    assert '<!-- POLICY_RESPONSE: BLOCKED' in content
    assert 'trust_guard_locked' in content


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
