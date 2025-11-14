#!/usr/bin/env python3
"""
Policy Response Runner — Phase XXV
Executes automated responses based on system policy level.

Policy Actions:
- GREEN: No automated actions
- YELLOW: Soft actions (integrity checks, schema validation, snapshot frequency↑)
- RED: Hard actions (self-healing, anchor regeneration, full verification, alerts)

Safety Gates:
- Trust guard unlocked
- Safety brake OFF
- Response rate limit not exceeded
- Manual unlock count within limits

Modes:
- Dry-run (default): Preview actions without execution
- Apply: Execute real actions (requires --apply flag)

Output:
- state/policy_response_preview.json (dry-run)
- state/policy_response_log.jsonl (apply mode)
- state/policy_response_undo_<id>.json (reversible actions)
"""

import argparse
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON atomically using tmp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix('.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp_path.replace(path)


def atomic_append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    """Append JSONL record atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


def with_retries(func, *args, max_attempts: int = 3, **kwargs):
    """Execute function with exponential backoff retries."""
    delays = [1, 3, 9]
    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            time.sleep(delays[attempt])
    raise RuntimeError("Max retries exceeded")


def create_fix_branch(error_msg: str) -> None:
    """Create fix branch on persistent error."""
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    branch_name = f"fix/policy-response-{timestamp}"
    try:
        subprocess.run(['git', 'checkout', '-b', branch_name], check=True, capture_output=True)
        print(f"Created fix branch: {branch_name}", file=sys.stderr)
    except subprocess.CalledProcessError:
        pass


def check_safety_gates() -> Dict[str, Any]:
    """
    Check all safety gates before executing actions.
    Returns dict with 'blocked' boolean and 'reason' string.
    """
    # Check trust guard lock
    trust_path = Path('trust_lock_state.json')
    if trust_path.exists():
        with open(trust_path, 'r', encoding='utf-8') as f:
            trust_state = json.load(f)
            if trust_state.get('locked', False):
                return {'blocked': True, 'reason': 'trust_guard_locked'}
    
    # Check safety brake
    brake_path = Path('forensics/safety_brake_state.json')
    if brake_path.exists():
        with open(brake_path, 'r', encoding='utf-8') as f:
            brake_state = json.load(f)
            if brake_state.get('is_engaged', False):
                return {'blocked': True, 'reason': 'safety_brake_engaged'}
    
    # Check response count (last 24h < 10 from adaptive response config)
    if brake_path.exists():
        with open(brake_path, 'r', encoding='utf-8') as f:
            brake_state = json.load(f)
            count = brake_state.get('response_count_24h', 0)
            max_count = brake_state.get('max_allowed', 10)
            if count >= max_count:
                return {'blocked': True, 'reason': f'rate_limit_exceeded_{count}/{max_count}'}
    
    # Check manual unlock count
    policy_path = Path('policy/trust_guard_policy.json')
    if policy_path.exists():
        with open(policy_path, 'r', encoding='utf-8') as f:
            policy = json.load(f)
            daily_limit = policy.get('manual_unlock_daily_limit', 3)
            
            trust_path = Path('trust_lock_state.json')
            if trust_path.exists():
                with open(trust_path, 'r', encoding='utf-8') as f:
                    trust_state = json.load(f)
                    manual_count = trust_state.get('manual_unlocks_today', 0)
                    if manual_count >= daily_limit:
                        return {'blocked': True, 'reason': f'manual_unlock_limit_{manual_count}/{daily_limit}'}
    
    return {'blocked': False, 'reason': None}


def plan_actions(policy: str) -> List[Dict[str, Any]]:
    """
    Plan actions based on policy level.
    Returns list of action dicts with 'name', 'command', 'reversible', 'undo_instruction'.
    """
    actions = []
    
    if policy == 'YELLOW':
        actions = [
            {
                'name': 'integrity_check',
                'command': ['python', 'scripts/workflow_utils/validate_governance_schemas.py'],
                'reversible': False,
                'undo_instruction': None
            },
            {
                'name': 'schema_validation',
                'command': ['python', 'scripts/workflow_utils/validate_integrity_registry_schema.py', 
                           '-r', 'exports/integrity_metrics_registry.csv', 
                           '-a', 'audit_summary.md'],
                'reversible': False,
                'undo_instruction': None
            }
        ]
    
    elif policy == 'RED':
        actions = [
            {
                'name': 'full_integrity_check',
                'command': ['python', 'scripts/workflow_utils/validate_governance_schemas.py'],
                'reversible': False,
                'undo_instruction': None
            },
            {
                'name': 'cold_storage_verification',
                'command': ['python', 'scripts/forensics/verify_cold_storage.py'],
                'reversible': False,
                'undo_instruction': None
            },
            {
                'name': 'integrity_anchor_mirror',
                'command': ['python', 'scripts/forensics/mirror_integrity_anchor.py'],
                'reversible': True,
                'undo_instruction': 'Restore previous anchor_chain.json from mirrors/anchor_chain.json.backup'
            }
        ]
    
    return actions


def execute_action(action: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    """
    Execute a single action.
    Returns result dict with 'success', 'stdout', 'stderr', 'duration'.
    """
    if dry_run:
        return {
            'success': True,
            'stdout': f"[DRY-RUN] Would execute: {' '.join(action['command'])}",
            'stderr': '',
            'duration': 0.0
        }
    
    start = time.time()
    try:
        result = subprocess.run(
            action['command'],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        duration = time.time() - start
        
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'duration': duration
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'stdout': '',
            'stderr': 'Action timed out after 300 seconds',
            'duration': 300.0
        }
    except Exception as e:
        return {
            'success': False,
            'stdout': '',
            'stderr': str(e),
            'duration': time.time() - start
        }


def run_response(policy: str, apply: bool) -> int:
    """Main response execution."""
    try:
        response_id = str(uuid.uuid4())
        timestamp = utc_now_iso()
        
        # Safety gate check
        safety_check = check_safety_gates()
        if safety_check['blocked']:
            blocked_report = {
                'response_id': response_id,
                'timestamp': timestamp,
                'policy': policy,
                'blocked': True,
                'reason': safety_check['reason']
            }
            
            reports_path = Path('reports/policy_response_blocked.json')
            with_retries(atomic_write_json, reports_path, blocked_report)
            
            # Append audit marker
            audit_path = Path('audit_summary.md')
            if audit_path.exists():
                with open(audit_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n<!-- POLICY_RESPONSE: BLOCKED {timestamp} reason: {safety_check['reason']} -->\n")
            
            print(json.dumps(blocked_report, indent=2))
            return 1  # Blocked, but not an error
        
        # Plan actions
        actions = plan_actions(policy)
        
        if not actions:
            print(f"No actions defined for policy: {policy}")
            return 0
        
        # Execute actions
        results = []
        for action in actions:
            result = execute_action(action, dry_run=not apply)
            results.append({
                'action': action['name'],
                'command': ' '.join(action['command']),
                'success': result['success'],
                'reversible': action['reversible'],
                'undo_instruction': action['undo_instruction'],
                'stdout': result['stdout'][:500],  # Truncate
                'stderr': result['stderr'][:500],
                'duration': result['duration']
            })
            
            # Create undo file for reversible actions
            if action['reversible'] and apply and result['success']:
                undo_path = Path(f"state/policy_response_undo_{response_id}_{action['name']}.json")
                undo_data = {
                    'response_id': response_id,
                    'action': action['name'],
                    'executed_at': timestamp,
                    'undo_instruction': action['undo_instruction']
                }
                with_retries(atomic_write_json, undo_path, undo_data)
        
        # Build summary
        summary = {
            'response_id': response_id,
            'timestamp': timestamp,
            'policy': policy,
            'mode': 'apply' if apply else 'dry-run',
            'safety_gates_passed': True,
            'actions_planned': len(actions),
            'actions_succeeded': sum(1 for r in results if r['success']),
            'results': results
        }
        
        # Write preview or log
        if apply:
            log_path = Path('state/policy_response_log.jsonl')
            with_retries(atomic_append_jsonl, log_path, summary)
        else:
            preview_path = Path('state/policy_response_preview.json')
            with_retries(atomic_write_json, preview_path, summary)
        
        print(json.dumps(summary, indent=2))
        
        # Check if any critical actions failed
        critical_failures = [r for r in results if not r['success'] and policy == 'RED']
        if critical_failures and apply:
            return 1
        
        return 0
        
    except Exception as e:
        print(f"Policy response failed: {e}", file=sys.stderr)
        create_fix_branch(str(e))
        
        # Append failure marker
        audit_path = Path('audit_summary.md')
        if audit_path.exists():
            with open(audit_path, 'a', encoding='utf-8') as f:
                f.write(f"\n<!-- POLICY_RESPONSE: FAILED {utc_now_iso()} -->\n")
        
        return 1


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description='Policy Response Runner')
    parser.add_argument('--policy', required=True, choices=['GREEN', 'YELLOW', 'RED'],
                       help='Policy level to respond to')
    parser.add_argument('--apply', action='store_true',
                       help='Execute real actions (default: dry-run)')
    args = parser.parse_args()
    
    if args.policy == 'GREEN':
        print("Policy is GREEN, no actions required")
        return 0
    
    return run_response(args.policy, args.apply)


if __name__ == '__main__':
    sys.exit(main())
