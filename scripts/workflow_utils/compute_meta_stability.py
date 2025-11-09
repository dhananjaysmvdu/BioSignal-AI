#!/usr/bin/env python3
"""Compute meta-learning stability index from governance history.

Inputs:
  - reports/history/versions.json: last 10 entries with coefficient fields

Outputs:
  - reports/meta_stability.json: MSI, variances, timestamp
  - reports/audit_summary.md: idempotent update between markers

Meta-Stability Index (MSI):
  - Computes variance for confidence_weight, drift_weight, human_feedback_weight
  - Normalized mean variance inverted to stability (low variance = high stability)
  - Clamped to [0,1], scaled to percentage
"""
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
from typing import List, Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
REPORTS = os.path.join(ROOT, 'reports')
VERSIONS_JSON = os.path.join(REPORTS, 'history', 'versions.json')
META_STABILITY_JSON = os.path.join(REPORTS, 'meta_stability.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')

BEGIN_MARKER = '<!-- META_STABILITY:BEGIN -->'
END_MARKER = '<!-- META_STABILITY:END -->'


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _variance(vals: List[float]) -> float:
    """Compute sample variance."""
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)


def _compute_msi(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Extract last 10 entries with coefficients
    entries = []
    for e in history[-10:]:
        cw = e.get('confidence_weight')
        dw = e.get('drift_weight')
        hw = e.get('human_feedback_weight')
        if cw is not None and dw is not None and hw is not None:
            try:
                entries.append({
                    'conf': float(cw),
                    'drift': float(dw),
                    'human': float(hw)
                })
            except Exception:
                pass
    if len(entries) < 2:
        # Insufficient data: assume perfect stability
        return {
            'meta_stability_index': 100.0,
            'variance_conf': 0.0,
            'variance_drift': 0.0,
            'variance_human': 0.0,
            'note': 'insufficient data for variance computation'
        }
    conf_vals = [e['conf'] for e in entries]
    drift_vals = [e['drift'] for e in entries]
    human_vals = [e['human'] for e in entries]
    var_conf = _variance(conf_vals)
    var_drift = _variance(drift_vals)
    var_human = _variance(human_vals)
    # Normalize variances (typical weight range ~[0,1], variance <<1)
    # Use simple mean of variances as instability measure
    mean_var = (var_conf + var_drift + var_human) / 3.0
    # MSI = 1 - normalized_variance; heuristic: scale variance by 10 for sensitivity
    # clamp to [0,1]
    normalized_var = min(1.0, mean_var * 10.0)
    msi = max(0.0, min(1.0, 1.0 - normalized_var)) * 100.0
    return {
        'meta_stability_index': round(msi, 1),
        'variance_conf': round(var_conf, 6),
        'variance_drift': round(var_drift, 6),
        'variance_human': round(var_human, 6)
    }


def _update_audit_summary(msi_data: Dict[str, Any], timestamp: str):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
        content = f.read()
    msi = msi_data['meta_stability_index']
    var_conf = msi_data['variance_conf']
    var_drift = msi_data['variance_drift']
    var_human = msi_data['variance_human']
    status = 'High' if msi >= 80 else ('Medium' if msi >= 60 else 'Low')
    block = f"""{BEGIN_MARKER}
## Meta-Learning Stability

**Meta-Stability Index:** {msi:.1f}% ({status})  
**Variance:** conf {var_conf:.6f} | drift {var_drift:.6f} | human {var_human:.6f}  
**Updated:** {timestamp}
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
    os.makedirs(REPORTS, exist_ok=True)
    history_data = _load_json(VERSIONS_JSON, [])
    if isinstance(history_data, dict):
        # legacy format
        history_data = history_data.get('history') or history_data.get('versions') or []
    if not isinstance(history_data, list):
        history_data = []
    msi_data = _compute_msi(history_data)
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'
    msi_data['timestamp'] = ts
    with open(META_STABILITY_JSON, 'w', encoding='utf-8') as f:
        json.dump(msi_data, f, indent=2)
    _update_audit_summary(msi_data, ts)
    print(json.dumps({
        'meta_stability_index': msi_data['meta_stability_index'],
        'written': META_STABILITY_JSON
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
