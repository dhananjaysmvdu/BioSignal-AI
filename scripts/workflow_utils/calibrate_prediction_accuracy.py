#!/usr/bin/env python3
"""Calibrate predictive adaptation accuracy.

Computes forecasting error between predicted ΔGHS from adaptation_plan.json and
actual observed ΔGHS from adaptation_outcomes.json.

Definitions:
  predicted_ΔGHS = adaptation_plan.predicted_improvement_percent (percentage points)
  actual_ΔGHS = latest outcome ghs_delta (percentage points)
  error = predicted_ΔGHS - actual_ΔGHS
  abs_error_pct = |error| / max(|actual_ΔGHS|, 1e-3) * 100

Maintains rolling mean absolute error across last N (default 30) entries in
reports/prediction_calibration.json

Reliability classification:
  mean_abs_error <= 10%  => High
  10% < error <= 25%     => Medium
  > 25%                  => Low

Graceful fallbacks:
  - Missing files => neutral calibration with unknown reliability.
  - Division by near zero guarded with 1e-3.

Outputs:
  - reports/prediction_calibration.json
  - audit_summary.md block <!-- PREDICTION_CALIBRATION:BEGIN/END -->
"""
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
REPORTS = os.path.join(ROOT, 'reports')
LOGS = os.path.join(ROOT, 'logs')
PLAN_JSON = os.path.join(REPORTS, 'adaptation_plan.json')
OUTCOMES_JSON = os.path.join(LOGS, 'adaptation_outcomes.json')
CALIB_JSON = os.path.join(REPORTS, 'prediction_calibration.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')
BEGIN_MARKER = '<!-- PREDICTION_CALIBRATION:BEGIN -->'
END_MARKER = '<!-- PREDICTION_CALIBRATION:END -->'
MAX_ENTRIES = 30


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _classify(mean_abs_error: float) -> str:
    if mean_abs_error <= 10:
        return 'High'
    if mean_abs_error <= 25:
        return 'Medium'
    return 'Low'


def _update_audit_summary(mean_err: float, reliability: str, ts: str):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    try:
        with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return
    block = f"""{BEGIN_MARKER}
Mean Forecast Error: {mean_err:.2f}%
Prediction Reliability: {reliability}
Timestamp: {ts}
{END_MARKER}"""
    if BEGIN_MARKER in content and END_MARKER in content:
        pattern = re.escape(BEGIN_MARKER) + r'.*?' + re.escape(END_MARKER)
        content = re.sub(pattern, block, content, flags=re.DOTALL)
    else:
        content = content.rstrip() + '\n\n' + block + '\n'
    with open(AUDIT_SUMMARY, 'w', encoding='utf-8') as f:
        f.write(content)


def main() -> int:
    os.makedirs(REPORTS, exist_ok=True)
    plan = _load_json(PLAN_JSON, {})
    outcomes = _load_json(OUTCOMES_JSON, [])
    if not isinstance(outcomes, list):
        outcomes = []

    predicted = float(plan.get('predicted_improvement_percent', 0.0)) if isinstance(plan, dict) else 0.0

    # Actual ΔGHS from latest outcome entry's ghs_delta; fallback to 0
    actual = 0.0
    if outcomes:
        # Use last entry with ghs_delta present
        for entry in reversed(outcomes):
            if entry.get('ghs_delta') is not None:
                try:
                    actual = float(entry['ghs_delta'])
                except Exception:
                    actual = 0.0
                break

    error = predicted - actual
    denom = max(abs(actual), 1e-3)
    abs_error_pct = abs(error) / denom * 100.0

    calib = _load_json(CALIB_JSON, {})
    history = calib.get('history', []) if isinstance(calib, dict) else []
    if not isinstance(history, list):
        history = []
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'
    history.append({'timestamp': ts, 'abs_error_pct': abs_error_pct})
    history = history[-MAX_ENTRIES:]
    mean_abs = sum(h.get('abs_error_pct', 0.0) for h in history) / len(history) if history else 0.0
    reliability = _classify(mean_abs) if history else 'Unknown'

    new_payload = {
        'timestamp': ts,
        'predicted_delta': predicted,
        'actual_delta': actual,
        'error': error,
        'abs_error_pct': abs_error_pct,
        'mean_abs_error_pct': mean_abs,
        'reliability': reliability,
        'history': history
    }
    with open(CALIB_JSON, 'w', encoding='utf-8') as f:
        json.dump(new_payload, f, indent=2)

    _update_audit_summary(mean_abs, reliability, ts)

    print(json.dumps({'status': 'ok', 'mean_abs_error_pct': mean_abs, 'reliability': reliability}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
