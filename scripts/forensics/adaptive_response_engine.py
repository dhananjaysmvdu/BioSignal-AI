#!/usr/bin/env python3
"""
Phase XXIV - Instruction 131-133: Adaptive Forensic Response Engine

Self-acting system that responds to forecast predictions with behavioral modes:
- Low risk: logging only
- Medium risk: soft actions (snapshots, integrity checks, schema validation)
- High risk: hard actions (self-healing, anchor regen, full verification)

Includes safety brake (rate limiter) and reversible actions ledger.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Add forensics directory to path for forensics_utils import
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forensics_utils import utc_now_iso, safe_write_json, log_forensics_event, append_audit_marker

FORENSICS_DIR = ROOT / 'forensics'
FORECAST_FILE = FORENSICS_DIR / 'forensics_anomaly_forecast.json'
RESPONSE_HISTORY = FORENSICS_DIR / 'response_history.jsonl'
REVERSIBLE_LEDGER = FORENSICS_DIR / 'reversible_actions_ledger.jsonl'
SAFETY_STATE_FILE = FORENSICS_DIR / 'safety_brake_state.json'
AUDIT_FILE = ROOT / 'audit_summary.md'

# Safety brake configuration
MAX_RESPONSES_PER_24H = 10
SAFETY_BRAKE_WINDOW_HOURS = 24

# Behavioral modes
class RiskMode:
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


class ResponseAction:
    """Enumeration of available automated actions."""
    # Soft actions (medium risk)
    INCREASE_SNAPSHOT_FREQUENCY = 'increase_snapshot_frequency'
    RUN_INTEGRITY_CHECK = 'run_integrity_check'
    VALIDATE_SCHEMAS = 'validate_schemas'
    
    # Hard actions (high risk)
    TRIGGER_SELF_HEALING = 'trigger_self_healing'
    REGENERATE_ANCHORS = 'regenerate_anchors'
    RUN_FULL_VERIFICATION = 'run_full_verification'
    CREATE_ALERT = 'create_alert'


def load_forecast() -> dict[str, Any] | None:
    """Load the latest forecast data."""
    if not FORECAST_FILE.exists():
        log_forensics_event({
            'error': 'forecast_file_missing',
            'path': str(FORECAST_FILE)
        })
        return None
    
    try:
        with FORECAST_FILE.open('r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log_forensics_event({
            'error': 'forecast_parse_failed',
            'exception': str(e)
        })
        return None


def check_safety_brake() -> tuple[bool, int]:
    """
    Check if safety brake is engaged.
    
    Returns:
        (is_engaged, response_count_24h)
    """
    if not RESPONSE_HISTORY.exists():
        return False, 0
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=SAFETY_BRAKE_WINDOW_HOURS)
    
    response_count = 0
    try:
        with RESPONSE_HISTORY.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    timestamp_str = record.get('timestamp', '')
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str)
                        if timestamp > cutoff:
                            response_count += 1
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception as e:
        log_forensics_event({
            'error': 'safety_brake_check_failed',
            'exception': str(e)
        })
        return False, 0
    
    is_engaged = response_count >= MAX_RESPONSES_PER_24H
    
    # Update safety state file
    safety_state = {
        'is_engaged': is_engaged,
        'response_count_24h': response_count,
        'max_allowed': MAX_RESPONSES_PER_24H,
        'last_check': utc_now_iso()
    }
    safe_write_json(SAFETY_STATE_FILE, safety_state)
    
    return is_engaged, response_count


def log_safety_brake_event() -> None:
    """Log safety brake engagement to response history."""
    event = {
        'response_id': str(uuid.uuid4()),
        'timestamp': utc_now_iso(),
        'event_type': 'SAFETY_BRAKE',
        'risk_level': None,
        'actions_taken': [],
        'message': f'Safety brake engaged: exceeded {MAX_RESPONSES_PER_24H} responses in {SAFETY_BRAKE_WINDOW_HOURS}h window',
        'status': 'parked'
    }
    
    RESPONSE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with RESPONSE_HISTORY.open('a', encoding='utf-8') as f:
        f.write(json.dumps(event) + '\n')
    
    log_forensics_event({
        'warning': 'safety_brake_engaged',
        'response_count': check_safety_brake()[1],
        'max_allowed': MAX_RESPONSES_PER_24H
    })


def log_response_entry(response_id: str, risk_level: str, actions: list[dict]) -> None:
    """Log response to history."""
    entry = {
        'response_id': response_id,
        'timestamp': utc_now_iso(),
        'event_type': 'ADAPTIVE_RESPONSE',
        'risk_level': risk_level,
        'actions_taken': actions,
        'status': 'completed'
    }
    
    RESPONSE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with RESPONSE_HISTORY.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')


def log_reversible_action(
    action_name: str,
    response_id: str,
    before_state: Any,
    after_state: Any,
    undo_instruction: str,
    reversible: bool = True
) -> None:
    """Log reversible action to ledger."""
    entry = {
        'action_id': str(uuid.uuid4()),
        'response_id': response_id,
        'timestamp': utc_now_iso(),
        'action': action_name,
        'before_state': before_state,
        'after_state': after_state,
        'undo_instruction': undo_instruction,
        'reversible': reversible
    }
    
    REVERSIBLE_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with REVERSIBLE_LEDGER.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')


def execute_soft_actions(response_id: str) -> list[dict]:
    """
    Execute medium-risk soft actions.
    
    Returns:
        List of action records.
    """
    actions = []
    
    # Action 1: Increase snapshot frequency
    try:
        # Log the intent to increase frequency (simulated)
        action = {
            'action': ResponseAction.INCREASE_SNAPSHOT_FREQUENCY,
            'status': 'simulated',
            'description': 'Snapshot frequency increased to 2x baseline'
        }
        actions.append(action)
        
        log_reversible_action(
            action_name=ResponseAction.INCREASE_SNAPSHOT_FREQUENCY,
            response_id=response_id,
            before_state={'frequency': 'baseline'},
            after_state={'frequency': '2x'},
            undo_instruction='Restore snapshot frequency to baseline via config update',
            reversible=True
        )
    except Exception as e:
        log_forensics_event({
            'error': 'soft_action_failed',
            'action': ResponseAction.INCREASE_SNAPSHOT_FREQUENCY,
            'exception': str(e)
        })
    
    # Action 2: Run integrity check
    try:
        # Run mirror integrity anchor (if script exists)
        script_path = ROOT / 'scripts' / 'forensics' / 'mirror_integrity_anchor.py'
        if script_path.exists():
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            action = {
                'action': ResponseAction.RUN_INTEGRITY_CHECK,
                'status': 'success' if result.returncode == 0 else 'failed',
                'description': 'Mirror integrity check executed'
            }
        else:
            action = {
                'action': ResponseAction.RUN_INTEGRITY_CHECK,
                'status': 'simulated',
                'description': 'Mirror integrity check (script not found)'
            }
        actions.append(action)
        
        log_reversible_action(
            action_name=ResponseAction.RUN_INTEGRITY_CHECK,
            response_id=response_id,
            before_state={'last_check': None},
            after_state={'last_check': utc_now_iso()},
            undo_instruction='No undo needed - read-only operation',
            reversible=False  # Read-only operation
        )
    except Exception as e:
        log_forensics_event({
            'error': 'soft_action_failed',
            'action': ResponseAction.RUN_INTEGRITY_CHECK,
            'exception': str(e)
        })
    
    # Action 3: Validate schemas
    try:
        action = {
            'action': ResponseAction.VALIDATE_SCHEMAS,
            'status': 'simulated',
            'description': 'Schema validation checks queued'
        }
        actions.append(action)
        
        log_reversible_action(
            action_name=ResponseAction.VALIDATE_SCHEMAS,
            response_id=response_id,
            before_state={'validation_status': 'unknown'},
            after_state={'validation_status': 'verified'},
            undo_instruction='No undo needed - validation is read-only',
            reversible=False
        )
    except Exception as e:
        log_forensics_event({
            'error': 'soft_action_failed',
            'action': ResponseAction.VALIDATE_SCHEMAS,
            'exception': str(e)
        })
    
    return actions


def execute_hard_actions(response_id: str) -> list[dict]:
    """
    Execute high-risk hard actions.
    
    Returns:
        List of action records.
    """
    actions = []
    
    # Action 1: Trigger self-healing
    try:
        action = {
            'action': ResponseAction.TRIGGER_SELF_HEALING,
            'status': 'simulated',
            'description': 'Self-healing mechanisms activated'
        }
        actions.append(action)
        
        log_reversible_action(
            action_name=ResponseAction.TRIGGER_SELF_HEALING,
            response_id=response_id,
            before_state={'healing_status': 'inactive'},
            after_state={'healing_status': 'active'},
            undo_instruction='Stop self-healing processes via system halt command',
            reversible=True
        )
    except Exception as e:
        log_forensics_event({
            'error': 'hard_action_failed',
            'action': ResponseAction.TRIGGER_SELF_HEALING,
            'exception': str(e)
        })
    
    # Action 2: Regenerate anchors
    try:
        # Run mirror integrity anchor to create new anchor
        script_path = ROOT / 'scripts' / 'forensics' / 'mirror_integrity_anchor.py'
        if script_path.exists():
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            action = {
                'action': ResponseAction.REGENERATE_ANCHORS,
                'status': 'success' if result.returncode == 0 else 'failed',
                'description': 'New integrity anchors generated'
            }
        else:
            action = {
                'action': ResponseAction.REGENERATE_ANCHORS,
                'status': 'simulated',
                'description': 'Anchor regeneration (script not found)'
            }
        actions.append(action)
        
        log_reversible_action(
            action_name=ResponseAction.REGENERATE_ANCHORS,
            response_id=response_id,
            before_state={'anchor_count': 'N'},
            after_state={'anchor_count': 'N+1'},
            undo_instruction='Delete latest anchor file from mirrors/ directory',
            reversible=True
        )
    except Exception as e:
        log_forensics_event({
            'error': 'hard_action_failed',
            'action': ResponseAction.REGENERATE_ANCHORS,
            'exception': str(e)
        })
    
    # Action 3: Run full verification
    try:
        # Run cold storage verification
        script_path = ROOT / 'scripts' / 'forensics' / 'verify_cold_storage.py'
        if script_path.exists():
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            action = {
                'action': ResponseAction.RUN_FULL_VERIFICATION,
                'status': 'success' if result.returncode == 0 else 'failed',
                'description': 'Full cold storage verification completed'
            }
        else:
            action = {
                'action': ResponseAction.RUN_FULL_VERIFICATION,
                'status': 'simulated',
                'description': 'Full verification (script not found)'
            }
        actions.append(action)
        
        log_reversible_action(
            action_name=ResponseAction.RUN_FULL_VERIFICATION,
            response_id=response_id,
            before_state={'verification_status': 'unknown'},
            after_state={'verification_status': 'verified'},
            undo_instruction='No undo needed - verification is read-only',
            reversible=False
        )
    except Exception as e:
        log_forensics_event({
            'error': 'hard_action_failed',
            'action': ResponseAction.RUN_FULL_VERIFICATION,
            'exception': str(e)
        })
    
    # Action 4: Create alert
    try:
        alert_entry = {
            'alert_id': str(uuid.uuid4()),
            'timestamp': utc_now_iso(),
            'severity': 'HIGH',
            'message': 'High forensic risk detected - automated response triggered',
            'response_id': response_id
        }
        
        action = {
            'action': ResponseAction.CREATE_ALERT,
            'status': 'success',
            'description': f'Alert created: {alert_entry["alert_id"]}'
        }
        actions.append(action)
        
        # Log alert to forensics error log
        log_forensics_event(alert_entry)
        
        log_reversible_action(
            action_name=ResponseAction.CREATE_ALERT,
            response_id=response_id,
            before_state={'alert_count': 'N'},
            after_state={'alert_count': 'N+1'},
            undo_instruction='Mark alert as acknowledged in alert management system',
            reversible=True
        )
    except Exception as e:
        log_forensics_event({
            'error': 'hard_action_failed',
            'action': ResponseAction.CREATE_ALERT,
            'exception': str(e)
        })
    
    return actions


def respond_to_forecast(forecast: dict[str, Any]) -> dict[str, Any]:
    """
    Execute adaptive response based on forecast risk level.
    
    Returns:
        Response summary.
    """
    risk_level = forecast.get('risk_level', 'low')
    response_id = str(uuid.uuid4())
    
    # Check safety brake
    brake_engaged, response_count = check_safety_brake()
    
    if brake_engaged:
        log_safety_brake_event()
        return {
            'response_id': response_id,
            'status': 'safety_brake_engaged',
            'risk_level': risk_level,
            'response_count_24h': response_count,
            'actions_taken': [],
            'message': f'Safety brake engaged: {response_count}/{MAX_RESPONSES_PER_24H} responses in 24h'
        }
    
    # Execute actions based on risk level
    actions = []
    
    if risk_level == RiskMode.LOW:
        # Low risk: logging only
        log_response_entry(response_id, risk_level, [])
        return {
            'response_id': response_id,
            'status': 'no_action',
            'risk_level': risk_level,
            'response_count_24h': response_count,
            'actions_taken': [],
            'message': 'Low risk detected - no action required'
        }
    
    elif risk_level == RiskMode.MEDIUM:
        # Medium risk: soft actions
        actions = execute_soft_actions(response_id)
        log_response_entry(response_id, risk_level, actions)
        return {
            'response_id': response_id,
            'status': 'soft_actions_executed',
            'risk_level': risk_level,
            'response_count_24h': response_count + 1,
            'actions_taken': actions,
            'message': f'Medium risk detected - {len(actions)} soft actions executed'
        }
    
    elif risk_level == RiskMode.HIGH:
        # High risk: hard actions
        actions = execute_hard_actions(response_id)
        log_response_entry(response_id, risk_level, actions)
        return {
            'response_id': response_id,
            'status': 'hard_actions_executed',
            'risk_level': risk_level,
            'response_count_24h': response_count + 1,
            'actions_taken': actions,
            'message': f'High risk detected - {len(actions)} hard actions executed'
        }
    
    else:
        # Unknown risk level
        log_forensics_event({
            'warning': 'unknown_risk_level',
            'risk_level': risk_level
        })
        return {
            'response_id': response_id,
            'status': 'unknown_risk_level',
            'risk_level': risk_level,
            'response_count_24h': response_count,
            'actions_taken': [],
            'message': f'Unknown risk level: {risk_level}'
        }


def main() -> None:
    """Main execution: read forecast and respond adaptively."""
    print("Adaptive Response Engine: Starting...")

    # Bypass mode: invoked by emergency override API to simulate response without actions
    if os.getenv("ADAPTIVE_BYPASS") == "1":
        marker = f"<!-- ADAPTIVE_RESPONSE: BYPASS {utc_now_iso()} -->"
        append_audit_marker(marker, ROOT)
        print("Adaptive Response Engine running in BYPASS MODE (override active).")
        return
    
    # Load forecast
    forecast = load_forecast()
    if not forecast:
        print("ERROR: Failed to load forecast", file=sys.stderr)
        sys.exit(1)
    
    print(f"Forecast loaded: risk_level={forecast.get('risk_level', 'unknown')}")
    
    # Execute adaptive response
    response = respond_to_forecast(forecast)
    
    print(f"Response ID: {response['response_id']}")
    print(f"Status: {response['status']}")
    print(f"Actions taken: {len(response['actions_taken'])}")
    print(f"24h response count: {response['response_count_24h']}/{MAX_RESPONSES_PER_24H}")
    
    # Append audit marker
    marker = f"<!-- ADAPTIVE_RESPONSE: {response['status'].upper()} {utc_now_iso()} -->"
    append_audit_marker(marker, ROOT)
    
    print(f"Response complete: {response['message']}")


if __name__ == '__main__':
    main()
