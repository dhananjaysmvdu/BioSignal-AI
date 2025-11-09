#!/usr/bin/env python3
"""Causal-based predictive adaptation planner.

Revised to use causal influence metrics (reports/causal_influence.json) to
propose the next optimal coefficient configuration and estimate projected
governance health improvement.

Computation per coefficient c:
    step_size = 0.02 * (1 + confidence_level / 100)
    Δc = influence_c * step_size
    new_c = clamp(c + Δc, 0, 1)

Projected improvement:
    Δpredicted = Σ(influence_c * Δc)
    predicted_improvement_percent = Δpredicted * 100

Inputs:
    - reports/causal_influence.json
    - configs/governance_policy.json
    - optional: reports/governance_health.json (for current GHS, else assume baseline 50)
    - optional: reports/meta_stability.json (not directly used but could enrich rationale)

Outputs:
    - reports/adaptation_plan.json (proposed coefficients & predicted improvement)
    - audit_summary.md marker block <!-- PREDICTIVE_PLAN:BEGIN/END -->

Graceful fallbacks:
    - Missing causal influence file ⇒ all influences = 0 (neutral proposal)
    - Missing policy ⇒ default coefficients {0.75, 0.5, 0.5}
    - Missing health ⇒ baseline current_GHS = 50.0
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
POLICY_JSON = os.path.join(CONFIGS, 'governance_policy.json')
CAUSAL_JSON = os.path.join(REPORTS, 'causal_influence.json')
HEALTH_JSON = os.path.join(REPORTS, 'governance_health.json')
META_STABILITY_JSON = os.path.join(REPORTS, 'meta_stability.json')  # optional
PLAN_JSON = os.path.join(REPORTS, 'adaptation_plan.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')

BEGIN_MARKER = '<!-- PREDICTIVE_PLAN:BEGIN -->'
END_MARKER = '<!-- PREDICTIVE_PLAN:END -->'


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def _build_plan(current_coeffs: Dict[str, float], causal: Dict[str, Any], current_ghs: float) -> Dict[str, Any]:
    influences = causal.get('normalized_influence', {}) if causal else {}
    confidence = causal.get('confidence', 0) if causal else 0
    # Step size formula
    step_size = 0.02 * (1 + (confidence / 100.0))

    proposed = {}
    deltas = {}
    # Only known keys
    for key in ['confidence_weight', 'drift_weight', 'human_feedback_weight']:
        base = float(current_coeffs.get(key, 0.0))
        influence = float(influences.get(key, 0.0))
        delta = influence * step_size
        new_val = _clamp(base + delta)
        proposed[key] = round(new_val, 4)
        deltas[key] = delta

    # Projected improvement using Σ(influence * Δc) * 100
    predicted_raw = sum(float(influences.get(k, 0.0)) * deltas[k] for k in deltas)
    predicted_improvement_pct = predicted_raw * 100.0
    projected_ghs = current_ghs + predicted_improvement_pct

    rationale_parts = []
    if influences:
        for k, v in influences.items():
            if abs(v) > 0:
                direction = 'increase' if v > 0 else 'decrease'
                rationale_parts.append(f"{k} {direction} (influence {v:+.2f})")
    if not rationale_parts:
        rationale_parts.append('No significant causal signals; keeping coefficients stable.')

    rationale = ' ; '.join(rationale_parts)

    return {
        'timestamp': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z',
        'confidence_level': confidence,
        'step_size': round(step_size, 4),
        'current_coefficients': current_coeffs,
        'proposed_coefficients': proposed,
        'predicted_improvement_percent': round(predicted_improvement_pct, 2),
        'projected_governance_health': round(projected_ghs, 2),
        'rationale': rationale,
        'influences_used': influences,
    }


def _update_audit_summary(plan: Dict[str, Any]):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    try:
        with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return

    ts = plan.get('timestamp', '')
    imp = plan.get('predicted_improvement_percent', 0.0)
    conf = plan.get('confidence_level', 0)
    coeffs = plan.get('proposed_coefficients', {})
    block = (
        f"{BEGIN_MARKER}\n"
        f"Predicted next-cycle improvement: {imp:+.1f}% (confidence {conf}%)\n"
        f"Proposed coefficients: conf={coeffs.get('confidence_weight', 0):.4f}, drift={coeffs.get('drift_weight', 0):.4f}, human={coeffs.get('human_feedback_weight', 0):.4f}\n"
        f"Timestamp: {ts}\n"
        f"{END_MARKER}"
    )

    if BEGIN_MARKER in content and END_MARKER in content:
        pattern = re.escape(BEGIN_MARKER) + r'.*?' + re.escape(END_MARKER)
        content = re.sub(pattern, block, content, flags=re.DOTALL)
    else:
        content = content.rstrip() + '\n\n' + block + '\n'

    with open(AUDIT_SUMMARY, 'w', encoding='utf-8') as f:
        f.write(content)


def main() -> int:
    os.makedirs(REPORTS, exist_ok=True)

    # Load policy coefficients
    policy = _load_json(POLICY_JSON, {})
    current_coeffs = policy.get('learning_coefficients') or {
        'confidence_weight': 0.75,
        'drift_weight': 0.5,
        'human_feedback_weight': 0.5
    }

    # Load causal influence (may be missing)
    causal = _load_json(CAUSAL_JSON, {})
    if not isinstance(causal, dict):
        causal = {}

    # Load current governance health (optional)
    health = _load_json(HEALTH_JSON, {})
    current_ghs = float(health.get('governance_health_score', 50.0)) if isinstance(health, dict) else 50.0

    plan = _build_plan(current_coeffs, causal, current_ghs)

    # Persist adaptation plan
    with open(PLAN_JSON, 'w', encoding='utf-8') as f:
        json.dump(plan, f, indent=2)

    _update_audit_summary(plan)

    print(json.dumps({
        'status': 'ok',
        'predicted_improvement_percent': plan['predicted_improvement_percent'],
        'confidence': plan['confidence_level']
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
