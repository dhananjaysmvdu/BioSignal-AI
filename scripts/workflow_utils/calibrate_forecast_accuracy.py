#!/usr/bin/env python3
"""Calibrate forecast accuracy of predictive adaptation planner.

Compares predicted projected governance health (from adaptation_plan.json)
against actual current governance health (from governance_health.json) and
records reliability metrics.

Definitions:
  projected_GHS = adaptation_plan.projected_governance_health (percentage)
  actual_GHS = governance_health.GovernanceHealthScore (percentage) OR fallback 0
  error = abs(actual_GHS - projected_GHS)
  accuracy = max(0, 100 - error)
  reliability = min(1.0, accuracy / 100)

Appends record to logs/forecast_accuracy.json and updates audit summary block:
<!-- FORECAST_CALIBRATION:BEGIN --> ... <!-- FORECAST_CALIBRATION:END -->

Graceful fallbacks:
  - Missing plan or health -> reliability marked "unavailable" and projected/actual set to 0.
  - Missing outcomes does not block (only for potential extension later).

Idempotent audit summary update via regex replacement.
"""
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
REPORTS = os.path.join(ROOT, 'reports')
LOGS = os.path.join(ROOT, 'logs')
PLAN_JSON = os.path.join(REPORTS, 'adaptation_plan.json')
HEALTH_JSON = os.path.join(REPORTS, 'governance_health.json')
OUTCOMES_JSON = os.path.join(LOGS, 'adaptation_outcomes.json')  # optional initial use
ACCURACY_LOG = os.path.join(LOGS, 'forecast_accuracy.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')
BEGIN_MARKER = '<!-- FORECAST_CALIBRATION:BEGIN -->'
END_MARKER = '<!-- FORECAST_CALIBRATION:END -->'


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _update_audit_summary(projected: float, actual: float, error: float, accuracy: float, reliability: float, ts: str, available: bool):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    try:
        with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return
    if not available:
        block = f"""{BEGIN_MARKER}\nForecast calibration: unavailable (missing prediction or actual)\nTimestamp: {ts}\n{END_MARKER}"""
    else:
        block = f"""{BEGIN_MARKER}\nForecast calibration: predicted {projected:.1f}%, actual {actual:.1f}% (error {error:.1f}%, reliability {accuracy:.1f}%)\nTimestamp: {ts}\n{END_MARKER}"""
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
    os.makedirs(REPORTS, exist_ok=True)
    plan = _load_json(PLAN_JSON, {})
    health = _load_json(HEALTH_JSON, {})

    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'

    projected = None
    actual = None
    if isinstance(plan, dict):
        try:
            projected = float(plan.get('projected_governance_health'))
        except Exception:
            projected = None
    if isinstance(health, dict):
        # health file might store key 'GovernanceHealthScore'
        for key in ('GovernanceHealthScore', 'governance_health_score', 'ghs'):
            if key in health:
                try:
                    actual = float(health[key])
                except Exception:
                    actual = None
                break

    available = projected is not None and actual is not None
    if not available:
        projected_val = 0.0
        actual_val = 0.0
        error = 0.0
        accuracy = 0.0
        reliability = 0.0
        _update_audit_summary(projected_val, actual_val, error, accuracy, reliability, ts, available=False)
        # Still append placeholder record for continuity
        prev_log = _load_json(ACCURACY_LOG, [])
        if not isinstance(prev_log, list):
            prev_log = []
        prev_log.append({
            'timestamp': ts,
            'predicted': projected_val,
            'actual': actual_val,
            'error': error,
            'accuracy': accuracy,
            'reliability': reliability,
            'available': False
        })
        try:
            with open(ACCURACY_LOG, 'w', encoding='utf-8') as f:
                json.dump(prev_log, f, indent=2)
        except Exception:
            pass
        print(json.dumps({'status': 'unavailable', 'reason': 'missing prediction or actual'}))
        return 0

    # Compute metrics
    projected_val = projected if projected is not None else 0.0
    actual_val = actual if actual is not None else 0.0
    error = abs(actual_val - projected_val)
    accuracy = max(0.0, 100.0 - error)
    reliability = min(1.0, accuracy / 100.0)

    # Append to log
    prev_log = _load_json(ACCURACY_LOG, [])
    if not isinstance(prev_log, list):
        prev_log = []
    prev_log.append({
        'timestamp': ts,
        'predicted': round(projected_val, 2),
        'actual': round(actual_val, 2),
        'error': round(error, 2),
        'accuracy': round(accuracy, 2),
        'reliability': round(reliability, 3),
        'available': True
    })
    try:
        with open(ACCURACY_LOG, 'w', encoding='utf-8') as f:
            json.dump(prev_log, f, indent=2)
    except Exception:
        pass

    _update_audit_summary(projected_val, actual_val, error, accuracy, reliability, ts, available=True)

    print(json.dumps({'status': 'ok', 'error': round(error,2), 'accuracy': round(accuracy,2), 'reliability': round(reliability,3)}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
