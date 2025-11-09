#!/usr/bin/env python3
"""Adapt governance policy based on Oversight Trust Index.

Reads:
  - configs/governance_policy.json (existing policy)
  - badges/trust_index.svg (extract numeric percentage from text/title)
Writes:
  - Updated configs/governance_policy.json with fields:
      audit_depth, confidence_threshold (adjusted), last_trust_index, last_policy_update (ISO timestamp)
  - Appends / replaces block in reports/audit_summary.md between TRUST_POLICY markers:
      <!-- TRUST_POLICY:BEGIN --> ... <!-- TRUST_POLICY:END -->
    containing a summary of changes.
  - Optionally records trust-driven policy event in logs/decision_trace.json

Threshold logic:
  trust_index >= 85: audit_depth -> "normal" (if higher), confidence_threshold += 0.05
  70 <= trust_index < 85: no depth change, confidence_threshold unchanged
  trust_index < 70: audit_depth -> "full", confidence_threshold -= 0.05

If inputs missing or parsing fails, trust_index defaults to 0 (worst-case) to enforce stricter policy.
Confidence threshold clamps to [0.0, 1.0].
Idempotent block replacement in audit_summary.
"""
from __future__ import annotations
import os, re, json, datetime
from typing import Any, Dict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
POLICY_JSON = os.path.join(ROOT, 'configs', 'governance_policy.json')
TRUST_SVG = os.path.join(ROOT, 'badges', 'trust_index.svg')
SUMMARY_MD = os.path.join(ROOT, 'reports', 'audit_summary.md')
TRACE_JSON = os.path.join(ROOT, 'logs', 'decision_trace.json')

TP_BEGIN = '<!-- TRUST_POLICY:BEGIN -->'
TP_END = '<!-- TRUST_POLICY:END -->'


def load_policy() -> Dict[str, Any]:
    if not os.path.exists(POLICY_JSON):
        return {}
    try:
        with open(POLICY_JSON, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except Exception:
        return {}


def parse_trust_index() -> float:
    if not os.path.exists(TRUST_SVG):
        return 0.0
    try:
        with open(TRUST_SVG, 'r', encoding='utf-8') as f:
            content = f.read()
        # look for percentage pattern like 72.34% or 80%
        m = re.search(r'(\d+(?:\.\d+)?)%', content)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return 0.0


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def adapt_policy(policy: Dict[str, Any], trust_pct: float) -> Dict[str, Any]:
    depth = policy.get('audit_depth', 'normal')
    conf_thr = float(policy.get('confidence_threshold', policy.get('confidence_threshold_pct', 0.75)))
    # If stored as percent > 1, assume percent and convert
    if conf_thr > 1:
        conf_thr = conf_thr / 100.0

    if trust_pct >= 85.0:
        # reduce rigor if currently higher than normal
        if depth in {'moderate', 'full'}:
            depth = 'normal'
        conf_thr = clamp(conf_thr + 0.05)
    elif trust_pct < 70.0:
        depth = 'full'
        conf_thr = clamp(conf_thr - 0.05)
    # else mid band: keep values

    policy['audit_depth'] = depth
    policy['confidence_threshold'] = round(conf_thr, 4)
    policy['last_trust_index'] = round(trust_pct, 2)
    policy['last_policy_update'] = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
    return policy


def write_policy(policy: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(POLICY_JSON), exist_ok=True)
    with open(POLICY_JSON, 'w', encoding='utf-8') as f:
        json.dump(policy, f, indent=2)


def update_summary(policy: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(SUMMARY_MD), exist_ok=True)
    existing = ''
    if os.path.exists(SUMMARY_MD):
        with open(SUMMARY_MD, 'r', encoding='utf-8') as f:
            existing = f.read()
    block = (
        f"{TP_BEGIN}\n"
        f"Oversight Trust Index: {policy['last_trust_index']}%\n"
        f"Adjusted Audit Depth: {policy['audit_depth']}\n"
        f"Updated Confidence Threshold: {policy['confidence_threshold']}\n"
        f"Last Update: {policy['last_policy_update']}\n"
        f"{TP_END}"
    )
    if TP_BEGIN in existing:
        updated = re.sub(rf'{re.escape(TP_BEGIN)}.*?{re.escape(TP_END)}', block, existing, flags=re.DOTALL)
    else:
        updated = existing.rstrip() + ('\n\n' if existing.strip() else '') + block + '\n'
    with open(SUMMARY_MD, 'w', encoding='utf-8') as f:
        f.write(updated)


def record_trace_event(policy: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(TRACE_JSON), exist_ok=True)
    trace = []
    if os.path.exists(TRACE_JSON):
        try:
            with open(TRACE_JSON, 'r', encoding='utf-8') as f:
                trace = json.load(f)
                if not isinstance(trace, list):
                    trace = []
        except Exception:
            trace = []
    event = {
        'timestamp': policy['last_policy_update'],
        'trust_policy_event': True,
        'trust_index_pct': policy['last_trust_index'],
        'new_audit_depth': policy['audit_depth'],
        'new_confidence_threshold': policy['confidence_threshold'],
        'source': 'update_policy_from_trust_index.py'
    }
    trace.append(event)
    with open(TRACE_JSON, 'w', encoding='utf-8') as f:
        json.dump(trace, f, indent=2)


def main() -> int:
    policy = load_policy()
    trust_pct = parse_trust_index()
    updated = adapt_policy(policy, trust_pct)
    write_policy(updated)
    update_summary(updated)
    record_trace_event(updated)  # optional refinement implemented
    print(json.dumps({'trust_index_pct': updated['last_trust_index'], 'audit_depth': updated['audit_depth'], 'confidence_threshold': updated['confidence_threshold']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
