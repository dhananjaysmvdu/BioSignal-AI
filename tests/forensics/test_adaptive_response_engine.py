#!/usr/bin/env python3
"""
Phase XXIV - Instruction 136: Regression Tests for Adaptive Response Logic

Test suite for adaptive forensic response engine with behavioral modes,
safety brake, and reversible actions ledger.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tmp_forensics(tmp_path, monkeypatch):
    """Create isolated forensics directory for testing."""
    forensics_dir = tmp_path / 'forensics'
    forensics_dir.mkdir(parents=True, exist_ok=True)
    
    # Monkeypatch the module-level paths
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'forensics'))
    
    import adaptive_response_engine
    monkeypatch.setattr(adaptive_response_engine, 'ROOT', tmp_path)
    monkeypatch.setattr(adaptive_response_engine, 'FORENSICS_DIR', forensics_dir)
    monkeypatch.setattr(adaptive_response_engine, 'FORECAST_FILE', forensics_dir / 'forensics_anomaly_forecast.json')
    monkeypatch.setattr(adaptive_response_engine, 'RESPONSE_HISTORY', forensics_dir / 'response_history.jsonl')
    monkeypatch.setattr(adaptive_response_engine, 'REVERSIBLE_LEDGER', forensics_dir / 'reversible_actions_ledger.jsonl')
    monkeypatch.setattr(adaptive_response_engine, 'SAFETY_STATE_FILE', forensics_dir / 'safety_brake_state.json')
    monkeypatch.setattr(adaptive_response_engine, 'AUDIT_FILE', tmp_path / 'audit_summary.md')
    
    # Create audit file
    (tmp_path / 'audit_summary.md').write_text('# Test Audit\n\n', encoding='utf-8')
    
    return forensics_dir


def create_forecast(forensics_dir: Path, risk_level: str) -> None:
    """Helper to create mock forecast file."""
    forecast = {
        'status': 'success',
        'forecast_generated_at': datetime.now(timezone.utc).isoformat(),
        'risk_level': risk_level,
        'predicted_anomalies_7d': [10.0] * 7 if risk_level == 'low' else 
                                   [20.0] * 7 if risk_level == 'medium' else 
                                   [30.0] * 7
    }
    forecast_file = forensics_dir / 'forensics_anomaly_forecast.json'
    with forecast_file.open('w', encoding='utf-8') as f:
        json.dump(forecast, f)


def test_low_risk_no_action(tmp_forensics, monkeypatch):
    """Test that low risk level triggers no actions."""
    import adaptive_response_engine
    
    # Re-apply monkeypatch for isolation
    monkeypatch.setattr(adaptive_response_engine, 'FORENSICS_DIR', tmp_forensics)
    monkeypatch.setattr(adaptive_response_engine, 'FORECAST_FILE', tmp_forensics / 'forensics_anomaly_forecast.json')
    monkeypatch.setattr(adaptive_response_engine, 'RESPONSE_HISTORY', tmp_forensics / 'response_history.jsonl')
    
    # Create low-risk forecast
    create_forecast(tmp_forensics, 'low')
    
    # Load and respond
    forecast = adaptive_response_engine.load_forecast()
    assert forecast is not None
    
    response = adaptive_response_engine.respond_to_forecast(forecast)
    
    # Validate no actions taken
    assert response['status'] == 'no_action'
    assert response['risk_level'] == 'low'
    assert len(response['actions_taken']) == 0
    assert 'no action required' in response['message'].lower()


def test_medium_risk_soft_actions(tmp_forensics, monkeypatch):
    """Test that medium risk triggers soft actions."""
    import adaptive_response_engine
    
    # Re-apply monkeypatch
    monkeypatch.setattr(adaptive_response_engine, 'FORENSICS_DIR', tmp_forensics)
    monkeypatch.setattr(adaptive_response_engine, 'FORECAST_FILE', tmp_forensics / 'forensics_anomaly_forecast.json')
    monkeypatch.setattr(adaptive_response_engine, 'RESPONSE_HISTORY', tmp_forensics / 'response_history.jsonl')
    monkeypatch.setattr(adaptive_response_engine, 'REVERSIBLE_LEDGER', tmp_forensics / 'reversible_actions_ledger.jsonl')
    
    # Create medium-risk forecast
    create_forecast(tmp_forensics, 'medium')
    
    # Load and respond
    forecast = adaptive_response_engine.load_forecast()
    response = adaptive_response_engine.respond_to_forecast(forecast)
    
    # Validate soft actions executed
    assert response['status'] == 'soft_actions_executed'
    assert response['risk_level'] == 'medium'
    assert len(response['actions_taken']) >= 3  # Should have 3 soft actions
    
    # Check action types
    action_names = [a['action'] for a in response['actions_taken']]
    assert adaptive_response_engine.ResponseAction.INCREASE_SNAPSHOT_FREQUENCY in action_names
    assert adaptive_response_engine.ResponseAction.RUN_INTEGRITY_CHECK in action_names
    assert adaptive_response_engine.ResponseAction.VALIDATE_SCHEMAS in action_names
    
    # Verify reversible ledger has entries
    ledger_file = tmp_forensics / 'reversible_actions_ledger.jsonl'
    assert ledger_file.exists()
    
    with ledger_file.open('r', encoding='utf-8') as f:
        entries = [json.loads(line) for line in f if line.strip()]
    
    assert len(entries) >= 3
    for entry in entries:
        assert 'action_id' in entry
        assert 'response_id' in entry
        assert 'undo_instruction' in entry


def test_high_risk_hard_actions(tmp_forensics, monkeypatch):
    """Test that high risk triggers hard actions."""
    import adaptive_response_engine
    
    # Re-apply monkeypatch
    monkeypatch.setattr(adaptive_response_engine, 'FORENSICS_DIR', tmp_forensics)
    monkeypatch.setattr(adaptive_response_engine, 'FORECAST_FILE', tmp_forensics / 'forensics_anomaly_forecast.json')
    monkeypatch.setattr(adaptive_response_engine, 'RESPONSE_HISTORY', tmp_forensics / 'response_history.jsonl')
    monkeypatch.setattr(adaptive_response_engine, 'REVERSIBLE_LEDGER', tmp_forensics / 'reversible_actions_ledger.jsonl')
    
    # Create high-risk forecast
    create_forecast(tmp_forensics, 'high')
    
    # Load and respond
    forecast = adaptive_response_engine.load_forecast()
    response = adaptive_response_engine.respond_to_forecast(forecast)
    
    # Validate hard actions executed
    assert response['status'] == 'hard_actions_executed'
    assert response['risk_level'] == 'high'
    assert len(response['actions_taken']) >= 4  # Should have 4 hard actions
    
    # Check action types
    action_names = [a['action'] for a in response['actions_taken']]
    assert adaptive_response_engine.ResponseAction.TRIGGER_SELF_HEALING in action_names
    assert adaptive_response_engine.ResponseAction.REGENERATE_ANCHORS in action_names
    assert adaptive_response_engine.ResponseAction.RUN_FULL_VERIFICATION in action_names
    assert adaptive_response_engine.ResponseAction.CREATE_ALERT in action_names


def test_safety_brake_engages(tmp_forensics, monkeypatch):
    """Test that safety brake engages after MAX_RESPONSES_PER_24H."""
    import adaptive_response_engine
    
    # Re-apply monkeypatch
    monkeypatch.setattr(adaptive_response_engine, 'FORENSICS_DIR', tmp_forensics)
    monkeypatch.setattr(adaptive_response_engine, 'FORECAST_FILE', tmp_forensics / 'forensics_anomaly_forecast.json')
    monkeypatch.setattr(adaptive_response_engine, 'RESPONSE_HISTORY', tmp_forensics / 'response_history.jsonl')
    monkeypatch.setattr(adaptive_response_engine, 'SAFETY_STATE_FILE', tmp_forensics / 'safety_brake_state.json')
    
    # Create medium-risk forecast
    create_forecast(tmp_forensics, 'medium')
    
    # Simulate 10 previous responses in last 24h
    response_history = tmp_forensics / 'response_history.jsonl'
    now = datetime.now(timezone.utc)
    
    with response_history.open('w', encoding='utf-8') as f:
        for i in range(10):
            entry = {
                'response_id': f'test-{i}',
                'timestamp': (now - timedelta(hours=i)).isoformat(),
                'event_type': 'ADAPTIVE_RESPONSE',
                'risk_level': 'medium',
                'actions_taken': [],
                'status': 'completed'
            }
            f.write(json.dumps(entry) + '\n')
    
    # Check safety brake
    is_engaged, count = adaptive_response_engine.check_safety_brake()
    assert is_engaged is True
    assert count >= 10
    
    # Try to respond - should be blocked
    forecast = adaptive_response_engine.load_forecast()
    response = adaptive_response_engine.respond_to_forecast(forecast)
    
    assert response['status'] == 'safety_brake_engaged'
    assert len(response['actions_taken']) == 0
    assert 'safety brake' in response['message'].lower()


def test_safety_brake_persists(tmp_forensics, monkeypatch):
    """Test that safety brake stays engaged until manual reset."""
    import adaptive_response_engine
    
    # Re-apply monkeypatch
    monkeypatch.setattr(adaptive_response_engine, 'FORENSICS_DIR', tmp_forensics)
    monkeypatch.setattr(adaptive_response_engine, 'FORECAST_FILE', tmp_forensics / 'forensics_anomaly_forecast.json')
    monkeypatch.setattr(adaptive_response_engine, 'RESPONSE_HISTORY', tmp_forensics / 'response_history.jsonl')
    monkeypatch.setattr(adaptive_response_engine, 'SAFETY_STATE_FILE', tmp_forensics / 'safety_brake_state.json')
    
    # Create forecast
    create_forecast(tmp_forensics, 'high')
    
    # Create 11 responses (exceeds MAX of 10)
    response_history = tmp_forensics / 'response_history.jsonl'
    now = datetime.now(timezone.utc)
    
    with response_history.open('w', encoding='utf-8') as f:
        for i in range(11):
            entry = {
                'response_id': f'test-{i}',
                'timestamp': (now - timedelta(minutes=i * 10)).isoformat(),
                'event_type': 'ADAPTIVE_RESPONSE',
                'risk_level': 'high',
                'actions_taken': [],
                'status': 'completed'
            }
            f.write(json.dumps(entry) + '\n')
    
    # First check
    is_engaged_1, _ = adaptive_response_engine.check_safety_brake()
    assert is_engaged_1 is True
    
    # Second check (without manual reset)
    is_engaged_2, _ = adaptive_response_engine.check_safety_brake()
    assert is_engaged_2 is True  # Should remain engaged
    
    # Verify safety state file
    safety_state_file = tmp_forensics / 'safety_brake_state.json'
    assert safety_state_file.exists()
    
    with safety_state_file.open('r', encoding='utf-8') as f:
        state = json.load(f)
    
    assert state['is_engaged'] is True
    assert state['response_count_24h'] >= 10


def test_reversible_ledger_valid_json(tmp_forensics, monkeypatch):
    """Test that reversible actions ledger contains valid JSON."""
    import adaptive_response_engine
    
    # Re-apply monkeypatch
    monkeypatch.setattr(adaptive_response_engine, 'FORENSICS_DIR', tmp_forensics)
    monkeypatch.setattr(adaptive_response_engine, 'FORECAST_FILE', tmp_forensics / 'forensics_anomaly_forecast.json')
    monkeypatch.setattr(adaptive_response_engine, 'RESPONSE_HISTORY', tmp_forensics / 'response_history.jsonl')
    monkeypatch.setattr(adaptive_response_engine, 'REVERSIBLE_LEDGER', tmp_forensics / 'reversible_actions_ledger.jsonl')
    
    # Create high-risk forecast to trigger multiple actions
    create_forecast(tmp_forensics, 'high')
    
    # Execute response
    forecast = adaptive_response_engine.load_forecast()
    adaptive_response_engine.respond_to_forecast(forecast)
    
    # Validate ledger
    ledger_file = tmp_forensics / 'reversible_actions_ledger.jsonl'
    assert ledger_file.exists()
    
    with ledger_file.open('r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            # Should parse without error
            entry = json.loads(line)
            
            # Validate required fields
            assert 'action_id' in entry
            assert 'response_id' in entry
            assert 'timestamp' in entry
            assert 'action' in entry
            assert 'before_state' in entry
            assert 'after_state' in entry
            assert 'undo_instruction' in entry
            assert 'reversible' in entry
            
            # Validate types
            assert isinstance(entry['reversible'], bool)
            assert isinstance(entry['undo_instruction'], str)
            
            # Validate timestamp format
            datetime.fromisoformat(entry['timestamp'])


def test_forecast_triggers_expected_responses(tmp_forensics, monkeypatch):
    """Test that forecast anomaly levels correctly trigger expected responses."""
    import adaptive_response_engine
    
    # Re-apply monkeypatch
    monkeypatch.setattr(adaptive_response_engine, 'FORENSICS_DIR', tmp_forensics)
    monkeypatch.setattr(adaptive_response_engine, 'FORECAST_FILE', tmp_forensics / 'forensics_anomaly_forecast.json')
    monkeypatch.setattr(adaptive_response_engine, 'RESPONSE_HISTORY', tmp_forensics / 'response_history.jsonl')
    monkeypatch.setattr(adaptive_response_engine, 'REVERSIBLE_LEDGER', tmp_forensics / 'reversible_actions_ledger.jsonl')
    
    # Test low → no action
    create_forecast(tmp_forensics, 'low')
    forecast_low = adaptive_response_engine.load_forecast()
    response_low = adaptive_response_engine.respond_to_forecast(forecast_low)
    assert response_low['status'] == 'no_action'
    
    # Test medium → soft actions
    create_forecast(tmp_forensics, 'medium')
    forecast_medium = adaptive_response_engine.load_forecast()
    response_medium = adaptive_response_engine.respond_to_forecast(forecast_medium)
    assert response_medium['status'] == 'soft_actions_executed'
    assert len(response_medium['actions_taken']) >= 3
    
    # Test high → hard actions
    create_forecast(tmp_forensics, 'high')
    forecast_high = adaptive_response_engine.load_forecast()
    response_high = adaptive_response_engine.respond_to_forecast(forecast_high)
    assert response_high['status'] == 'hard_actions_executed'
    assert len(response_high['actions_taken']) >= 4


def test_response_history_logging(tmp_forensics, monkeypatch):
    """Test that all responses are logged to history."""
    import adaptive_response_engine
    
    # Re-apply monkeypatch
    monkeypatch.setattr(adaptive_response_engine, 'FORENSICS_DIR', tmp_forensics)
    monkeypatch.setattr(adaptive_response_engine, 'FORECAST_FILE', tmp_forensics / 'forensics_anomaly_forecast.json')
    monkeypatch.setattr(adaptive_response_engine, 'RESPONSE_HISTORY', tmp_forensics / 'response_history.jsonl')
    monkeypatch.setattr(adaptive_response_engine, 'REVERSIBLE_LEDGER', tmp_forensics / 'reversible_actions_ledger.jsonl')
    
    # Execute multiple responses
    for risk_level in ['low', 'medium', 'high']:
        create_forecast(tmp_forensics, risk_level)
        forecast = adaptive_response_engine.load_forecast()
        adaptive_response_engine.respond_to_forecast(forecast)
    
    # Validate history file
    history_file = tmp_forensics / 'response_history.jsonl'
    assert history_file.exists()
    
    with history_file.open('r', encoding='utf-8') as f:
        entries = [json.loads(line) for line in f if line.strip()]
    
    # Should have 3 entries (low, medium, high)
    assert len(entries) >= 3
    
    # Validate entry structure
    for entry in entries:
        assert 'response_id' in entry
        assert 'timestamp' in entry
        assert 'event_type' in entry
        assert 'risk_level' in entry
        assert 'actions_taken' in entry
        assert 'status' in entry


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
