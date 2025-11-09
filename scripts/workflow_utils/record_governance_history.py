#!/usr/bin/env python3
"""Record governance history snapshot for Governance Pulse timeline.

Inputs:
  - reports/governance_health.json
  - configs/governance_policy.json
  - reports/audit_summary.md (optional, not strictly needed)
  - badges/trust_index.svg (regex to extract %)

Output:
  - reports/history/versions.json: array of last 30 entries with keys
      timestamp (UTC ISO Z), ghs, audit_frequency, confidence_threshold, trust_index

Graceful defaults when inputs missing.
"""
from __future__ import annotations
import os, json, re
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
REPORTS = os.path.join(ROOT, 'reports')
CONFIGS = os.path.join(ROOT, 'configs')
BADGES = os.path.join(ROOT, 'badges')

HEALTH_JSON = os.path.join(REPORTS, 'governance_health.json')
POLICY_JSON = os.path.join(CONFIGS, 'governance_policy.json')
SUMMARY_MD = os.path.join(REPORTS, 'audit_summary.md')
TRUST_SVG = os.path.join(BADGES, 'trust_index.svg')
VERSIONS_JSON = os.path.join(REPORTS, 'history', 'versions.json')


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _extract_trust(svg_path: str) -> float:
    if not os.path.exists(svg_path):
        return 0.0
    try:
        with open(svg_path, 'r', encoding='utf-8') as f:
            s = f.read()
        m = re.search(r'(\d+(?:\.\d+)?)%', s)
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0


def main() -> int:
    os.makedirs(os.path.dirname(VERSIONS_JSON), exist_ok=True)
    health = _load_json(HEALTH_JSON, {}) or {}
    policy = _load_json(POLICY_JSON, {}) or {}
    ghs = float(health.get('GovernanceHealthScore') or 0.0)
    audit_freq = policy.get('audit_frequency') or '7d'
    lc = policy.get('learning_coefficients', {}) or {}
    conf_weight = lc.get('confidence_weight', policy.get('confidence_threshold', 0.75))
    drift_weight = lc.get('drift_weight', 0.5)
    human_weight = lc.get('human_feedback_weight', 0.5)
    # Normalize/convert to float, provide sane fallbacks
    def _to_float(v, default):
        try:
            return float(v)
        except Exception:
            return default
    conf_weight = _to_float(conf_weight, 0.75)
    drift_weight = _to_float(drift_weight, 0.5)
    human_weight = _to_float(human_weight, 0.5)
    trust = _extract_trust(TRUST_SVG)
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'
    entry = {
        'timestamp': ts,
        'ghs': round(ghs, 1),
        'audit_frequency': str(audit_freq),
        'confidence_threshold': round(conf_weight, 4),  # retained for backward compatibility nomenclature
        'trust_index': round(trust, 1),
        'confidence_weight': round(conf_weight, 4),
        'drift_weight': round(drift_weight, 4),
        'human_feedback_weight': round(human_weight, 4),
    }
    history: List[Dict[str, Any]] = []
    cur = _load_json(VERSIONS_JSON, None)
    if isinstance(cur, list):
        history = cur
    elif isinstance(cur, dict):
        # legacy formats under keys
        for k in ('history', 'versions', 'entries'):
            if isinstance(cur.get(k), list):
                history = cur[k]
                break
    # Append and keep last 30
    history.append(entry)
    history = history[-30:]
    with open(VERSIONS_JSON, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2)
    print(json.dumps({'written': len(history), 'latest': entry}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
