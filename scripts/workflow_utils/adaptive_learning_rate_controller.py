#!/usr/bin/env python3
"""Adaptive meta-learning rate controller using Meta-Stability Index feedback.

Uses MSI as a signal to modulate coefficient update rates:
- High stability (MSI ≥85) → accelerate adaptation (×1.2)
- Medium stability (60-84) → nominal rate (×1.0)
- Low stability (<60) → dampen fluctuations (×0.5)

Inputs:
  - reports/meta_stability.json: current MSI
  - configs/governance_policy.json: coefficients to scale

Outputs:
  - configs/governance_policy.json: updated with scaled coefficients, learning_rate_factor, timestamp
  - reports/audit_summary.md: idempotent marker-based update
"""
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
REPORTS = os.path.join(ROOT, 'reports')
CONFIGS = os.path.join(ROOT, 'configs')
META_STABILITY_JSON = os.path.join(REPORTS, 'meta_stability.json')
POLICY_JSON = os.path.join(CONFIGS, 'governance_policy.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')

BEGIN_MARKER = '<!-- ADAPTIVE_LEARNING:BEGIN -->'
END_MARKER = '<!-- ADAPTIVE_LEARNING:END -->'


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp value to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def _compute_learning_rate_factor(msi: float) -> Tuple[float, str]:
    """
    Compute learning rate scaling factor from MSI.
    Returns (factor, description).
    """
    if msi >= 85.0:
        return (1.2, 'accelerate adaptation')
    elif msi >= 60.0:
        return (1.0, 'nominal')
    else:
        return (0.5, 'dampen adaptation')


def _apply_adaptive_rate(policy: Dict[str, Any], msi: float, timestamp: str) -> Dict[str, Any]:
    """
    Apply adaptive learning rate scaling to coefficients.
    """
    lc = policy.get('learning_coefficients', {})
    if not lc:
        # Initialize with defaults if missing
        lc = {
            'confidence_weight': 0.75,
            'drift_weight': 0.5,
            'human_feedback_weight': 0.5
        }
    conf_w = float(lc.get('confidence_weight', 0.75))
    drift_w = float(lc.get('drift_weight', 0.5))
    human_w = float(lc.get('human_feedback_weight', 0.5))
    
    rate_factor, rate_desc = _compute_learning_rate_factor(msi)
    
    # Scale coefficients proportionally
    # Interpretation: rate_factor modulates how aggressively we adapt from baseline
    # For simplicity, scale the deviation from 0.5 (mid-point) and re-center
    def _scale_coefficient(val: float, factor: float) -> float:
        # Scale deviation from neutral (0.5)
        deviation = val - 0.5
        scaled = 0.5 + deviation * factor
        return _clamp(scaled)
    
    conf_w_new = _scale_coefficient(conf_w, rate_factor)
    drift_w_new = _scale_coefficient(drift_w, rate_factor)
    human_w_new = _scale_coefficient(human_w, rate_factor)
    
    # Update policy
    policy['learning_coefficients'] = {
        'confidence_weight': round(conf_w_new, 4),
        'drift_weight': round(drift_w_new, 4),
        'human_feedback_weight': round(human_w_new, 4)
    }
    policy['learning_rate_factor'] = round(rate_factor, 2)
    policy['last_learning_rate_adjustment'] = timestamp
    
    return {
        'msi': msi,
        'rate_factor': rate_factor,
        'rate_desc': rate_desc,
        'conf_w': round(conf_w_new, 4),
        'drift_w': round(drift_w_new, 4),
        'human_w': round(human_w_new, 4)
    }


def _update_audit_summary(result: Dict[str, Any], timestamp: str):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
        content = f.read()
    
    msi = result['msi']
    rf = result['rate_factor']
    desc = result['rate_desc']
    conf = result['conf_w']
    drift = result['drift_w']
    human = result['human_w']
    
    block = f"""{BEGIN_MARKER}
## Adaptive Learning Rate Controller

**MSI:** {msi:.1f}% → Applied **{desc}** (×{rf})  
**Updated coefficients:** confidence={conf:.2f}, drift={drift:.2f}, human_feedback={human:.2f}  
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
    
    # Load MSI (default to nominal if missing)
    msi_data = _load_json(META_STABILITY_JSON, {})
    msi = float(msi_data.get('meta_stability_index', 70.0))  # default to medium stability
    
    # Load policy
    policy = _load_json(POLICY_JSON, {})
    if not policy:
        # Initialize minimal policy if missing
        policy = {
            'audit_depth': 'standard',
            'drift_threshold': 0.15,
            'audit_frequency': '7d',
            'learning_coefficients': {
                'confidence_weight': 0.75,
                'drift_weight': 0.5,
                'human_feedback_weight': 0.5
            }
        }
    
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'
    
    # Apply adaptive rate
    result = _apply_adaptive_rate(policy, msi, ts)
    
    # Write updated policy
    with open(POLICY_JSON, 'w', encoding='utf-8') as f:
        json.dump(policy, f, indent=2)
    
    # Update audit summary
    _update_audit_summary(result, ts)
    
    print(json.dumps({
        'msi': result['msi'],
        'learning_rate_factor': result['rate_factor'],
        'coefficients': {
            'confidence_weight': result['conf_w'],
            'drift_weight': result['drift_w'],
            'human_feedback_weight': result['human_w']
        }
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
