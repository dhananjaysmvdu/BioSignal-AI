#!/usr/bin/env python3
"""Evaluate adaptation outcomes for governance self-assessment and learning.

Analyzes effectiveness of governance adaptations by computing deltas in:
- Governance Health Score (GHS)
- Meta-Stability Index (MSI)
- Policy coefficients

Classifies outcomes to build historical effectiveness database for future weighting.

Inputs:
  - reports/governance_health.json: current GHS
  - reports/meta_stability.json: current MSI
  - configs/governance_policy.json: current coefficients
  - logs/adaptation_outcomes.json: historical outcomes (for comparison)

Outputs:
  - logs/adaptation_outcomes.json: appended with latest evaluation (keep last 100)
  - reports/audit_summary.md: idempotent marker-based update
"""
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
REPORTS = os.path.join(ROOT, 'reports')
CONFIGS = os.path.join(ROOT, 'configs')
LOGS = os.path.join(ROOT, 'logs')

GOVERNANCE_HEALTH_JSON = os.path.join(REPORTS, 'governance_health.json')
META_STABILITY_JSON = os.path.join(REPORTS, 'meta_stability.json')
POLICY_JSON = os.path.join(CONFIGS, 'governance_policy.json')
OUTCOMES_JSON = os.path.join(LOGS, 'adaptation_outcomes.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')

BEGIN_MARKER = '<!-- ADAPTATION_OUTCOMES:BEGIN -->'
END_MARKER = '<!-- ADAPTATION_OUTCOMES:END -->'

MAX_OUTCOMES = 100  # Keep last 100 evaluations


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _get_previous_outcome(outcomes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Get the most recent prior outcome for comparison."""
    if outcomes:
        return outcomes[-1]
    return None


def _classify_outcome(ghs_delta: float, msi_delta: float) -> str:
    """
    Classify adaptation outcome based on health and stability changes.
    
    Improved: Both GHS and MSI increased (or one increased significantly)
    Degraded: Either GHS or MSI decreased significantly
    Neutral: Small changes (|Δ| < 1%)
    """
    threshold = 1.0  # 1% threshold for significance
    
    if abs(ghs_delta) < threshold and abs(msi_delta) < threshold:
        return 'neutral'
    
    # Check for improvement: both positive or one strongly positive
    if ghs_delta > 0 and msi_delta > 0:
        return 'improved'
    if ghs_delta > threshold * 2 and msi_delta >= 0:
        return 'improved'
    if msi_delta > threshold * 2 and ghs_delta >= 0:
        return 'improved'
    
    # Check for degradation: any significant negative
    if ghs_delta < -threshold or msi_delta < -threshold:
        return 'degraded'
    
    return 'neutral'


def _evaluate_adaptation(
    current_ghs: float,
    current_msi: float,
    current_coeffs: Dict[str, float],
    previous: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Evaluate the effectiveness of the last adaptation cycle.
    """
    if not previous:
        # First run: no prior data to compare
        return {
            'ghs_delta': 0.0,
            'msi_delta': 0.0,
            'outcome': 'neutral',
            'note': 'first evaluation, no prior baseline'
        }
    
    prev_ghs = float(previous.get('current_ghs', 0.0))
    prev_msi = float(previous.get('current_msi', 0.0))
    
    ghs_delta = current_ghs - prev_ghs
    msi_delta = current_msi - prev_msi
    
    outcome = _classify_outcome(ghs_delta, msi_delta)
    
    result = {
        'ghs_delta': round(ghs_delta, 2),
        'msi_delta': round(msi_delta, 2),
        'outcome': outcome
    }
    
    # If improved, record the effective coefficients for future reference
    if outcome == 'improved':
        result['effective_coefficients'] = current_coeffs.copy()
    
    return result


def _update_audit_summary(evaluation: Dict[str, Any], timestamp: str):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
        content = f.read()
    
    outcome = evaluation['outcome']
    ghs_delta = evaluation['ghs_delta']
    msi_delta = evaluation['msi_delta']
    
    # Format outcome with deltas
    if outcome == 'neutral':
        outcome_text = 'Neutral (minimal change)'
    else:
        outcome_text = f"{outcome.capitalize()} ({ghs_delta:+.1f} GHS, {msi_delta:+.1f} MSI)"
    
    # Include coefficients if available
    coeff_text = ''
    if 'effective_coefficients' in evaluation:
        ec = evaluation['effective_coefficients']
        coeff_text = f"\n**Effective Coefficients:** Confidence={ec.get('confidence_weight', 0):.2f}, Drift={ec.get('drift_weight', 0):.2f}, Human={ec.get('human_feedback_weight', 0):.2f}"
    
    block = f"""{BEGIN_MARKER}
## Last Adaptation Outcome

**Status:** {outcome_text}{coeff_text}  
**Evaluated:** {timestamp}
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
    os.makedirs(LOGS, exist_ok=True)
    os.makedirs(REPORTS, exist_ok=True)
    
    # Load current state
    health_data = _load_json(GOVERNANCE_HEALTH_JSON, {})
    current_ghs = float(health_data.get('GovernanceHealthScore', 0.0))
    
    msi_data = _load_json(META_STABILITY_JSON, {})
    current_msi = float(msi_data.get('meta_stability_index', 0.0))
    
    policy_data = _load_json(POLICY_JSON, {})
    lc = policy_data.get('learning_coefficients', {})
    current_coeffs = {
        'confidence_weight': float(lc.get('confidence_weight', 0.75)),
        'drift_weight': float(lc.get('drift_weight', 0.5)),
        'human_feedback_weight': float(lc.get('human_feedback_weight', 0.5))
    }
    
    # Load historical outcomes
    outcomes = _load_json(OUTCOMES_JSON, [])
    if not isinstance(outcomes, list):
        outcomes = []
    
    # Get previous outcome for comparison
    previous = _get_previous_outcome(outcomes)
    
    # Evaluate current adaptation
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'
    evaluation = _evaluate_adaptation(current_ghs, current_msi, current_coeffs, previous)
    
    # Build outcome record
    outcome_record = {
        'timestamp': ts,
        'current_ghs': round(current_ghs, 1),
        'current_msi': round(current_msi, 1),
        'current_coefficients': current_coeffs,
        **evaluation
    }
    
    # Append and trim to last MAX_OUTCOMES
    outcomes.append(outcome_record)
    outcomes = outcomes[-MAX_OUTCOMES:]
    
    # Write outcomes log
    with open(OUTCOMES_JSON, 'w', encoding='utf-8') as f:
        json.dump(outcomes, f, indent=2)
    
    # Update audit summary
    _update_audit_summary(evaluation, ts)
    
    # Output summary
    print(json.dumps({
        'outcome': evaluation['outcome'],
        'ghs_delta': evaluation['ghs_delta'],
        'msi_delta': evaluation['msi_delta'],
        'total_evaluations': len(outcomes)
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
