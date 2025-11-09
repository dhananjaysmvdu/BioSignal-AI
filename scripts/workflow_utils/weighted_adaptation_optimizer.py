#!/usr/bin/env python3
"""Weighted adaptation optimizer using historical effectiveness data.

Leverages adaptation_outcomes.json to identify successful coefficient configurations
and blends current coefficients toward historically effective values.

Learning strategy:
- Extract "improved" outcomes from history
- Compute mean coefficients across successful configurations
- Blend current values toward mean using success-rate-weighted factor
- More successful history → stronger bias toward proven configurations

Inputs:
  - logs/adaptation_outcomes.json: historical outcomes with effectiveness data
  - configs/governance_policy.json: current coefficients

Outputs:
  - configs/governance_policy.json: updated with weighted-optimized coefficients
  - reports/audit_summary.md: idempotent marker-based update
"""
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
REPORTS = os.path.join(ROOT, 'reports')
CONFIGS = os.path.join(ROOT, 'configs')
LOGS = os.path.join(ROOT, 'logs')

OUTCOMES_JSON = os.path.join(LOGS, 'adaptation_outcomes.json')
POLICY_JSON = os.path.join(CONFIGS, 'governance_policy.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')

BEGIN_MARKER = '<!-- WEIGHTED_ADAPTATION:BEGIN -->'
END_MARKER = '<!-- WEIGHTED_ADAPTATION:END -->'

MIN_IMPROVED_OUTCOMES = 3  # Minimum successful outcomes needed for weighting


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp value to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def _extract_improved_outcomes(outcomes: List[Dict[str, Any]], last_n: int = 20) -> List[Dict[str, Any]]:
    """
    Extract recent outcomes classified as 'improved' with effective coefficients.
    """
    improved = []
    for outcome in outcomes[-last_n:]:
        if outcome.get('outcome') == 'improved' and 'effective_coefficients' in outcome:
            improved.append(outcome)
    return improved


def _compute_mean_effective_coefficients(improved: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """
    Compute mean of effective coefficients across improved outcomes.
    """
    if not improved:
        return None
    
    conf_vals = []
    drift_vals = []
    human_vals = []
    
    for outcome in improved:
        ec = outcome.get('effective_coefficients', {})
        conf_vals.append(float(ec.get('confidence_weight', 0.0)))
        drift_vals.append(float(ec.get('drift_weight', 0.0)))
        human_vals.append(float(ec.get('human_feedback_weight', 0.0)))
    
    if not conf_vals:
        return None
    
    return {
        'confidence_weight': sum(conf_vals) / len(conf_vals),
        'drift_weight': sum(drift_vals) / len(drift_vals),
        'human_feedback_weight': sum(human_vals) / len(human_vals)
    }


def _blend_coefficients(
    current: Dict[str, float],
    mean_effective: Dict[str, float],
    success_rate: float
) -> Dict[str, float]:
    """
    Blend current coefficients toward mean effective values using success-weighted alpha.
    
    α = 0.2 × success_rate  (learning rate scales with historical success)
    new = (1 - α) × current + α × mean_effective
    """
    alpha = 0.2 * success_rate
    
    blended = {}
    for key in ['confidence_weight', 'drift_weight', 'human_feedback_weight']:
        current_val = current.get(key, 0.5)
        mean_val = mean_effective.get(key, current_val)
        new_val = (1.0 - alpha) * current_val + alpha * mean_val
        blended[key] = _clamp(round(new_val, 4))
    
    return blended


def _update_audit_summary(
    success_rate: float,
    updated_coeffs: Dict[str, float],
    timestamp: str,
    skipped: bool = False
):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if skipped:
        block = f"""{BEGIN_MARKER}
## Weighted Optimization

**Status:** Skipped (insufficient successful outcomes for learning)  
**Timestamp:** {timestamp}
{END_MARKER}"""
    else:
        conf = updated_coeffs['confidence_weight']
        drift = updated_coeffs['drift_weight']
        human = updated_coeffs['human_feedback_weight']
        
        block = f"""{BEGIN_MARKER}
## Weighted Optimization Applied

**Success Rate:** {success_rate*100:.1f}%  
**Strategy:** Blended toward historically effective coefficients  
**Updated Coefficients:** conf={conf:.2f}, drift={drift:.2f}, human={human:.2f}  
**Timestamp:** {timestamp}
{END_MARKER}"""
    
    if BEGIN_MARKER in content and END_MARKER in content:
        # Replace existing block
        pattern = re.escape(BEGIN_MARKER) + r'.*?' + re.escape(END_MARKER)
        content = re.sub(pattern, block, content, flags=re.DOTALL)
    else:
        # Append block
        content = content.rstrip() + '\n\n' + block + '\n'
    
    with open(AUDIT_SUMMARY, 'w', encoding='utf-8') as f:
        f.write(content)


def main() -> int:
    os.makedirs(CONFIGS, exist_ok=True)
    os.makedirs(REPORTS, exist_ok=True)
    
    # Load outcomes history
    outcomes = _load_json(OUTCOMES_JSON, [])
    if not isinstance(outcomes, list):
        outcomes = []
    
    # Load current policy
    policy = _load_json(POLICY_JSON, {})
    if not policy:
        policy = {
            'learning_coefficients': {
                'confidence_weight': 0.75,
                'drift_weight': 0.5,
                'human_feedback_weight': 0.5
            }
        }
    
    current_coeffs = policy.get('learning_coefficients', {})
    if not current_coeffs:
        current_coeffs = {
            'confidence_weight': 0.75,
            'drift_weight': 0.5,
            'human_feedback_weight': 0.5
        }
    
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'
    
    # Extract improved outcomes
    improved = _extract_improved_outcomes(outcomes, last_n=20)
    total_recent = len(outcomes[-20:]) if outcomes else 0
    
    # Check if sufficient data for weighting
    if len(improved) < MIN_IMPROVED_OUTCOMES:
        # Insufficient data: skip weighting
        _update_audit_summary(0.0, current_coeffs, ts, skipped=True)
        print(json.dumps({
            'status': 'skipped',
            'reason': 'insufficient_improved_outcomes',
            'improved_count': len(improved),
            'required': MIN_IMPROVED_OUTCOMES
        }))
        return 0
    
    # Compute mean effective coefficients
    mean_effective = _compute_mean_effective_coefficients(improved)
    if not mean_effective:
        # No valid effective coefficients found
        _update_audit_summary(0.0, current_coeffs, ts, skipped=True)
        print(json.dumps({
            'status': 'skipped',
            'reason': 'no_valid_effective_coefficients'
        }))
        return 0
    
    # Calculate success rate
    success_rate = len(improved) / max(total_recent, 1)
    
    # Blend toward effective coefficients
    updated_coeffs = _blend_coefficients(current_coeffs, mean_effective, success_rate)
    
    # Update policy
    policy['learning_coefficients'] = updated_coeffs
    policy['last_weighted_update'] = ts
    policy['success_rate'] = round(success_rate * 100, 1)
    
    # Write updated policy
    with open(POLICY_JSON, 'w', encoding='utf-8') as f:
        json.dump(policy, f, indent=2)
    
    # Update audit summary
    _update_audit_summary(success_rate, updated_coeffs, ts)
    
    # Output summary
    print(json.dumps({
        'status': 'applied',
        'success_rate': round(success_rate * 100, 1),
        'improved_count': len(improved),
        'total_recent': total_recent,
        'updated_coefficients': updated_coeffs
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
