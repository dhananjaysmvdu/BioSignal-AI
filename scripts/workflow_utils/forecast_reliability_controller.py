#!/usr/bin/env python3
"""Forecast Reliability Feedback Controller.

Dynamically modulates adaptation aggressiveness (learning_rate_factor and
confidence_threshold) based on historical forecast accuracy reliability.

Reads last 10 reliability entries from logs/forecast_accuracy.json, computes
an average reliability and derives a reliability_weight:
  reliability_weight = clamp(avg_reliability, 0.5, 1.0)

If reliability < 0.8, aggressiveness is reduced (already handled by clamp but
also recorded as status note).

Updates governance_policy.json with:
  - reliability_weight
  - adjusted learning_rate_factor (existing * reliability_weight if present; else baseline 1.0 * weight)
  - adjusted confidence_threshold (baseline or existing confidence_weight scaled)
  - last_reliability_update timestamp

Audit summary marker block:
<!-- RELIABILITY_FEEDBACK:BEGIN -->
Forecast reliability (10-run avg): 0.87
Adjusted learning_rate_factor: 0.91
Adjusted confidence_threshold: 0.73
Timestamp: 2025-11-10T09:20Z
<!-- RELIABILITY_FEEDBACK:END -->

Graceful fallbacks:
  - Missing forecast_accuracy.json → reliability_weight=1.0 (no penalty)
  - Missing policy → initialize minimal baseline
  - Missing confidence fields → use confidence_weight or 0.75 baseline
"""
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LOGS = os.path.join(ROOT, 'logs')
CONFIGS = os.path.join(ROOT, 'configs')
REPORTS = os.path.join(ROOT, 'reports')
ACCURACY_LOG = os.path.join(LOGS, 'forecast_accuracy.json')
POLICY_JSON = os.path.join(CONFIGS, 'governance_policy.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')
BEGIN_MARKER = '<!-- RELIABILITY_FEEDBACK:BEGIN -->'
END_MARKER = '<!-- RELIABILITY_FEEDBACK:END -->'

MIN_WEIGHT = 0.5
MAX_WEIGHT = 1.0
WINDOW = 10


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _compute_reliability_weight(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not entries:
        return {'avg_reliability': 1.0, 'weight': 1.0, 'status': 'no data → neutral weight'}
    # Take last WINDOW entries
    recent = entries[-WINDOW:]
    rels = [float(e.get('reliability', 0.0)) for e in recent if isinstance(e.get('reliability'), (int, float))]
    if not rels:
        return {'avg_reliability': 1.0, 'weight': 1.0, 'status': 'no valid reliabilities → neutral'}
    avg_rel = sum(rels) / len(rels)
    weight = _clamp(avg_rel, MIN_WEIGHT, MAX_WEIGHT)
    status = 'dampened (<0.8 avg)' if avg_rel < 0.8 else 'stable'
    return {'avg_reliability': avg_rel, 'weight': weight, 'status': status}


def _update_policy(policy: Dict[str, Any], rel_data: Dict[str, Any], ts: str) -> Dict[str, Any]:
    # Ensure base policy shape
    if not policy:
        policy = {
            'audit_frequency': '7d',
            'learning_coefficients': {
                'confidence_weight': 0.75,
                'drift_weight': 0.5,
                'human_feedback_weight': 0.5
            },
            'drift_threshold': 0.15
        }
    lc = policy.get('learning_coefficients', {}) or {}
    confidence_weight = float(lc.get('confidence_weight', 0.75))
    # Existing learning_rate_factor optional
    existing_lrf = float(policy.get('learning_rate_factor', 1.0))
    base_conf_threshold = float(policy.get('confidence_threshold', confidence_weight))

    reliability_weight = float(rel_data['weight'])
    adjusted_lrf = existing_lrf * reliability_weight
    adjusted_conf_threshold = base_conf_threshold * reliability_weight

    policy['reliability_weight'] = round(reliability_weight, 3)
    policy['learning_rate_factor'] = round(adjusted_lrf, 3)
    policy['confidence_threshold'] = round(adjusted_conf_threshold, 3)
    policy['last_reliability_update'] = ts

    return {
        'avg_reliability': rel_data['avg_reliability'],
        'reliability_weight': reliability_weight,
        'adjusted_learning_rate_factor': adjusted_lrf,
        'adjusted_confidence_threshold': adjusted_conf_threshold,
        'status': rel_data['status']
    }


def _update_audit_summary(data: Dict[str, Any], ts: str):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    try:
        with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return
    block = (
        f"{BEGIN_MARKER}\n"
        f"Forecast reliability (10-run avg): {data['avg_reliability']:.2f}\n"
        f"Adjusted learning_rate_factor: {data['adjusted_learning_rate_factor']:.2f}\n"
        f"Adjusted confidence_threshold: {data['adjusted_confidence_threshold']:.2f}\n"
        f"Timestamp: {ts}\n"
        f"{END_MARKER}"
    )
    if BEGIN_MARKER in content and END_MARKER in content:
        pattern = re.escape(BEGIN_MARKER) + r'.*?' + re.escape(END_MARKER)
        content = re.sub(pattern, block, content, flags=re.DOTALL)
    else:
        content = content.rstrip() + '\n\n' + block + '\n'
    try:
        with open(AUDIT_SUMMARY, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception:
        pass


def main() -> int:
    os.makedirs(LOGS, exist_ok=True)
    os.makedirs(CONFIGS, exist_ok=True)
    os.makedirs(REPORTS, exist_ok=True)

    acc_log = _load_json(ACCURACY_LOG, [])
    if not isinstance(acc_log, list):
        acc_log = []
    policy = _load_json(POLICY_JSON, {})

    rel_data = _compute_reliability_weight(acc_log)
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'

    updated = _update_policy(policy, rel_data, ts)

    # Persist policy
    try:
        with open(POLICY_JSON, 'w', encoding='utf-8') as f:
            json.dump(policy, f, indent=2)
    except Exception:
        pass

    _update_audit_summary(updated, ts)

    print(json.dumps({
        'avg_reliability': round(updated['avg_reliability'], 4),
        'reliability_weight': round(updated['reliability_weight'], 3),
        'learning_rate_factor': round(updated['adjusted_learning_rate_factor'], 3),
        'confidence_threshold': round(updated['adjusted_confidence_threshold'], 3),
        'status': updated['status']
    }))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
