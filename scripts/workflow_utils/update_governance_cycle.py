#!/usr/bin/env python3
"""Update governance meta-learning coefficients and audit schedule based on Governance Health Score (GHS).

Reads:
  reports/governance_health.json -> GovernanceHealthScore
  configs/governance_policy.json -> existing policy (created with defaults if missing)
  logs/decision_trace.json -> append event

Policy adaptation:
  If GHS >= 85: confidence_weight += 0.05 (<=1.0); human_feedback_weight -= 0.05 (>=0.3); next audit in 14 days
  If 70 <= GHS < 85: unchanged coefficients; next audit in 7 days
  If GHS < 70: confidence_weight -= 0.05 (>=0.0); human_feedback_weight += 0.05 (<=0.9); next audit in 2 days

Writes:
  - Updated configs/governance_policy.json (preserving other fields, adding last_cycle_update & last_ghs)
  - logs/decision_trace.json appended event
  - reports/audit_summary.md GOVERNANCE_CYCLE block idempotently

Graceful degradation: missing governance_health.json => GHS=0 (critical mode).
"""
from __future__ import annotations
import os, json, datetime, re
from typing import Any, Dict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HEALTH_JSON = os.path.join(ROOT, 'reports', 'governance_health.json')
POLICY_JSON = os.path.join(ROOT, 'configs', 'governance_policy.json')
TRACE_JSON = os.path.join(ROOT, 'logs', 'decision_trace.json')
SUMMARY_MD = os.path.join(ROOT, 'reports', 'audit_summary.md')

GC_BEGIN = '<!-- GOVERNANCE_CYCLE:BEGIN -->'
GC_END = '<!-- GOVERNANCE_CYCLE:END -->'


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data: Any):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def _now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def load_policy() -> Dict[str, Any]:
    policy = _load_json(POLICY_JSON, {})
    # Ensure learning_coefficients present
    lc = policy.get('learning_coefficients') or {}
    if 'confidence_weight' not in lc:
        lc['confidence_weight'] = 0.7
    if 'drift_weight' not in lc:
        lc['drift_weight'] = 0.6
    if 'human_feedback_weight' not in lc:
        lc['human_feedback_weight'] = 0.5
    policy['learning_coefficients'] = lc
    # Ensure audit_depth
    if 'audit_depth' not in policy:
        policy['audit_depth'] = 'normal'
    return policy


def adapt(policy: Dict[str, Any], ghs: float) -> Dict[str, Any]:
    lc = policy['learning_coefficients']
    conf = float(lc.get('confidence_weight', 0.7))
    hfw = float(lc.get('human_feedback_weight', 0.5))

    if ghs >= 85.0:
        conf = min(1.0, conf + 0.05)
        hfw = max(0.3, hfw - 0.05)
        interval_days = 14
    elif ghs >= 70.0:
        interval_days = 7
    else:
        conf = max(0.0, conf - 0.05)
        hfw = min(0.9, hfw + 0.05)
        interval_days = 2

    lc['confidence_weight'] = round(conf, 4)
    lc['human_feedback_weight'] = round(hfw, 4)

    # schedule next audit date
    next_date = (datetime.datetime.utcnow() + datetime.timedelta(days=interval_days)).date().isoformat()
    policy['next_audit_date'] = next_date
    policy['audit_frequency'] = f"{interval_days}d"
    policy['learning_coefficients'] = lc
    policy['last_cycle_update'] = _now_iso()
    policy['last_ghs'] = round(ghs, 2)
    return policy


def append_trace(ghs: float, policy: Dict[str, Any]):
    trace = _load_json(TRACE_JSON, [])
    if not isinstance(trace, list):
        trace = []
    event = {
        'timestamp': policy['last_cycle_update'],
        'event': 'governance_cycle_update',
        'GHS': round(ghs, 2),
        'new_audit_frequency': policy.get('audit_frequency'),
        'adjusted_coefficients': {
            'confidence_weight': policy['learning_coefficients']['confidence_weight'],
            'human_feedback_weight': policy['learning_coefficients']['human_feedback_weight'],
        }
    }
    trace.append(event)
    _save_json(TRACE_JSON, trace)


def update_summary(ghs: float, policy: Dict[str, Any]):
    existing = ''
    if os.path.exists(SUMMARY_MD):
        with open(SUMMARY_MD, 'r', encoding='utf-8') as f:
            existing = f.read()
    block = (
        f"{GC_BEGIN}\n"
        f"Governance Health Score (last): {ghs:.2f}%\n"
        f"New Audit Frequency: {policy.get('audit_frequency')}\n"
        f"Confidence Weight: {policy['learning_coefficients']['confidence_weight']} | Human Feedback Weight: {policy['learning_coefficients']['human_feedback_weight']}\n"
        f"Updated: {policy['last_cycle_update']}\n"
        f"{GC_END}"
    )
    if GC_BEGIN in existing:
        new = re.sub(rf'{re.escape(GC_BEGIN)}.*?{re.escape(GC_END)}', block, existing, flags=re.DOTALL)
    else:
        new = existing.rstrip() + ('\n\n' if existing.strip() else '') + block + '\n'
    os.makedirs(os.path.dirname(SUMMARY_MD), exist_ok=True)
    with open(SUMMARY_MD, 'w', encoding='utf-8') as f:
        f.write(new)


def main() -> int:
    health = _load_json(HEALTH_JSON, {})
    ghs = float(health.get('GovernanceHealthScore', 0.0))
    policy = load_policy()
    policy = adapt(policy, ghs)
    _save_json(POLICY_JSON, policy)
    append_trace(ghs, policy)
    update_summary(ghs, policy)
    print(json.dumps({
        'ghs': round(ghs,2),
        'audit_frequency': policy.get('audit_frequency'),
        'confidence_weight': policy['learning_coefficients']['confidence_weight'],
        'human_feedback_weight': policy['learning_coefficients']['human_feedback_weight']
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
