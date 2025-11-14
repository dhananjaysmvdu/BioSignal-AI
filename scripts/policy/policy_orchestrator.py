#!/usr/bin/env python3
"""
Policy Orchestrator Engine — Phase XXV
Combines all subsystem signals into unified policy decision.

Policy Levels:
- GREEN: All systems healthy, no action required
- YELLOW: Moderate risk detected, watch + soft actions
- RED: Critical state, blocking policy + self-healing

Inputs:
- trust_lock_state.json
- exports/integrity_metrics_registry.csv
- federation/weighted_consensus.json
- federation/reputation_index.json
- forensics/response_history.jsonl
- forensics/forensics_anomaly_forecast.json

Output:
- state/policy_state.json
- state/policy_state_log.jsonl

Safety:
- Atomic writes (tmp → rename)
- 3-step retry with exponential backoff (1s, 3s, 9s)
- Fix-branch creation on persistent FS error
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
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
    """Create fix branch on persistent FS error."""
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    branch_name = f"fix/policy-orchestrator-{timestamp}"
    try:
        subprocess.run(['git', 'checkout', '-b', branch_name], check=True, capture_output=True)
        print(f"Created fix branch: {branch_name}", file=sys.stderr)
    except subprocess.CalledProcessError:
        pass


def load_trust_lock_state() -> Dict[str, Any]:
    """Load trust guard lock state."""
    path = Path('trust_lock_state.json')
    if not path.exists():
        return {'locked': False}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_integrity_metrics() -> float:
    """Load latest integrity score from registry."""
    path = Path('exports/integrity_metrics_registry.csv')
    if not path.exists():
        return 100.0
    
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            return 100.0
        return float(rows[-1]['integrity_score'])


def load_weighted_consensus() -> float:
    """Load weighted consensus agreement percentage."""
    path = Path('federation/weighted_consensus.json')
    if not path.exists():
        return 100.0
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get('weighted_agreement_pct', 100.0)


def load_reputation_index() -> float:
    """Load average reputation score."""
    path = Path('federation/reputation_index.json')
    if not path.exists():
        return 100.0
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        peers = data.get('peers', [])
        if not peers:
            return 100.0
        scores = [p.get('reputation_score', 100.0) for p in peers]
        return sum(scores) / len(scores)


def load_forecast_risk() -> str:
    """Load forecast risk level."""
    path = Path('forensics/forensics_anomaly_forecast.json')
    if not path.exists():
        return 'low'
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get('risk_level', 'low').lower()


def load_recent_responses() -> int:
    """Count recent adaptive responses (last 10 entries)."""
    path = Path('forensics/response_history.jsonl')
    if not path.exists():
        return 0
    
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        return len(lines[-10:]) if lines else 0


def compute_policy(
    trust_locked: bool,
    integrity_score: float,
    consensus_pct: float,
    reputation_score: float,
    forecast_risk: str,
    recent_responses: int
) -> str:
    """
    Compute overall system policy based on subsystem signals.
    
    RED triggers:
    - Trust guard locked
    - Integrity < 90%
    - Consensus < 85%
    - Forecast risk = high
    - Recent responses >= 8 (high adaptive activity)
    
    YELLOW triggers:
    - Integrity 90-95%
    - Consensus 85-90%
    - Reputation < 80%
    - Forecast risk = medium
    - Recent responses 4-7
    
    GREEN: All healthy
    """
    # RED conditions
    if trust_locked:
        return 'RED'
    if integrity_score < 90.0:
        return 'RED'
    if consensus_pct < 85.0:
        return 'RED'
    if forecast_risk == 'high':
        return 'RED'
    if recent_responses >= 8:
        return 'RED'
    
    # YELLOW conditions
    if integrity_score < 95.0:
        return 'YELLOW'
    if consensus_pct < 90.0:
        return 'YELLOW'
    if reputation_score < 80.0:
        return 'YELLOW'
    if forecast_risk == 'medium':
        return 'YELLOW'
    if recent_responses >= 4:
        return 'YELLOW'
    
    return 'GREEN'


def append_audit_marker(policy: str) -> None:
    """Append idempotent audit marker to audit_summary.md."""
    audit_path = Path('audit_summary.md')
    if not audit_path.exists():
        return
    
    marker_line = f"<!-- POLICY_ORCHESTRATION: UPDATED {utc_now_iso()} policy={policy} -->"
    
    with open(audit_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Idempotent: replace existing marker or append
    marker_start = '<!-- POLICY_ORCHESTRATION:'
    if marker_start in content:
        lines = content.split('\n')
        new_lines = [line for line in lines if not line.strip().startswith(marker_start)]
        new_lines.append(marker_line)
        content = '\n'.join(new_lines)
        if not content.endswith('\n'):
            content += '\n'
        with open(audit_path, 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        with open(audit_path, 'a', encoding='utf-8') as f:
            f.write(marker_line + '\n')


def run_orchestrator() -> int:
    """Main orchestrator execution."""
    try:
        # Load all subsystem inputs
        trust_state = load_trust_lock_state()
        integrity = load_integrity_metrics()
        consensus = load_weighted_consensus()
        reputation = load_reputation_index()
        forecast = load_forecast_risk()
        responses = load_recent_responses()
        
        trust_locked = trust_state.get('locked', False)
        
        # Compute policy
        policy = compute_policy(
            trust_locked=trust_locked,
            integrity_score=integrity,
            consensus_pct=consensus,
            reputation_score=reputation,
            forecast_risk=forecast,
            recent_responses=responses
        )
        
        # Build output state
        timestamp = utc_now_iso()
        state = {
            'policy': policy,
            'evaluated_at': timestamp,
            'inputs': {
                'trust_locked': trust_locked,
                'integrity_score': integrity,
                'consensus_pct': consensus,
                'reputation_score': reputation,
                'forecast_risk': forecast,
                'recent_responses': responses
            },
            'thresholds': {
                'red_integrity': 90.0,
                'red_consensus': 85.0,
                'red_responses': 8,
                'yellow_integrity': 95.0,
                'yellow_consensus': 90.0,
                'yellow_reputation': 80.0,
                'yellow_responses': 4
            }
        }
        
        # Write outputs with retries
        state_path = Path('state/policy_state.json')
        log_path = Path('state/policy_state_log.jsonl')
        
        with_retries(atomic_write_json, state_path, state)
        
        log_entry = {
            'timestamp': timestamp,
            'policy': policy,
            'trust_locked': trust_locked,
            'integrity': integrity,
            'consensus': consensus,
            'reputation': reputation,
            'forecast': forecast,
            'responses': responses
        }
        with_retries(atomic_append_jsonl, log_path, log_entry)
        
        # Append audit marker
        append_audit_marker(policy)
        
        print(json.dumps(state, indent=2))
        return 0
        
    except Exception as e:
        print(f"Policy orchestration failed: {e}", file=sys.stderr)
        create_fix_branch(str(e))
        return 1


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description='Policy Orchestrator Engine')
    parser.add_argument('--run', action='store_true', help='Execute policy orchestration')
    args = parser.parse_args()
    
    if args.run:
        return run_orchestrator()
    
    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
