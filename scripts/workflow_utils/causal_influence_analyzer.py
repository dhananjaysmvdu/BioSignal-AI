#!/usr/bin/env python3
"""Causal influence analyzer for governance adaptation coefficients.

Computes a simple covariance-based influence metric for each meta-learning
coefficient against combined governance performance deltas (GHS and MSI).

Metric per coefficient c:
    influence_c = cov(Δc, (ΔGHS + ΔMSI/2)) / var(Δc)

We derive Δc from successive effective/current coefficients recorded in
adaptation_outcomes.json. For each outcome entry we look at its
`current_coefficients` (post-adaptation state) and compute difference vs
previous entry's coefficients to obtain Δc.

Edge cases & safeguards:
  - <5 usable samples: outputs neutral influences (0) with low confidence.
  - Zero variance in Δc: influence set to 0 to avoid division by zero.
  - Normalization: Sum of absolute influences scaled so Σ|w_i| = 1 when any
    non-zero present; else all remain 0.
  - Labels: positive => 'stabilizing', negative => 'destabilizing', zero => 'neutral'.
  - Confidence level (%) scaled by min( (usable_samples / 20)*100, 95 ). Floor at 20% if samples >=5.

Outputs:
  - reports/causal_influence.json
  - Marker block in reports/audit_summary.md
"""
from __future__ import annotations
import os
import json
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LOGS = os.path.join(ROOT, 'logs')
REPORTS = os.path.join(ROOT, 'reports')
CONFIGS = os.path.join(ROOT, 'configs')

OUTCOMES_JSON = os.path.join(LOGS, 'adaptation_outcomes.json')
POLICY_JSON = os.path.join(CONFIGS, 'governance_policy.json')  # for baseline if needed
OUTPUT_JSON = os.path.join(REPORTS, 'causal_influence.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')

BEGIN_MARKER = '<!-- CAUSAL_INFLUENCE:BEGIN -->'
END_MARKER = '<!-- CAUSAL_INFLUENCE:END -->'
MIN_SAMPLES = 5

COEFF_KEYS = [
    'confidence_weight',
    'drift_weight',
    'human_feedback_weight'
]


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _extract_series(outcomes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, float]], List[float], List[float]]:
    """Extract coefficient snapshots and performance deltas.

    Returns tuple: (coeff_snapshots, ghs_deltas, msi_deltas)
    Each snapshot is a dict of coefficients after adaptation for that entry.
    Filters out entries lacking required fields.
    """
    coeffs_series = []
    ghs_deltas = []
    msi_deltas = []
    for o in outcomes:
        if o.get('note') == 'first evaluation, no prior baseline':
            # Skip first baseline entry
            continue
        cur = o.get('current_coefficients') or {}
        ghs_delta = o.get('ghs_delta')
        msi_delta = o.get('msi_delta')
        if cur and ghs_delta is not None and msi_delta is not None:
            coeffs_series.append({k: float(cur.get(k, 0.0)) for k in COEFF_KEYS})
            ghs_deltas.append(float(ghs_delta))
            msi_deltas.append(float(msi_delta))
    return coeffs_series, ghs_deltas, msi_deltas


def _compute_deltas(coeffs_series: List[Dict[str, float]]) -> Dict[str, List[float]]:
    """Compute successive differences Δc for each coefficient key."""
    deltas = {k: [] for k in COEFF_KEYS}
    if not coeffs_series:
        return deltas
    prev = coeffs_series[0]
    for cur in coeffs_series[1:]:
        for k in COEFF_KEYS:
            deltas[k].append(cur[k] - prev[k])
        prev = cur
    return deltas


def _variance(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return sum((v - mean) ** 2 for v in values) / (n - 1)


def _covariance(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n != len(ys) or n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / (n - 1)


def _label(value: float) -> str:
    if value > 0:
        return 'stabilizing'
    if value < 0:
        return 'destabilizing'
    return 'neutral'


def _normalize(influences: Dict[str, float]) -> Dict[str, float]:
    total_abs = sum(abs(v) for v in influences.values())
    if total_abs <= 0:
        return {k: 0.0 for k in influences}
    return {k: v / total_abs for k, v in influences.items()}


def _confidence(samples: int) -> int:
    if samples < MIN_SAMPLES:
        return int((samples / MIN_SAMPLES) * 20)  # <5 scaled below 20%
    # scale up to 95% at 20 samples
    conf = int(min((samples / 20) * 100, 95))
    return max(conf, 20)


def _update_audit_summary(data: Dict[str, Any]):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = [BEGIN_MARKER, 'Causal Influence Analysis:']
    for k in COEFF_KEYS:
        val = data['normalized_influence'][k]
        label = data['labels'][k]
        sign = '+' if val > 0 else '-' if val < 0 else '±'
        lines.append(f"{k.replace('_', ' ').title()} → {sign}{abs(val):.2f} ({label})")
    lines.append(f"Confidence Level: {data['confidence']}%")
    lines.append(f"Timestamp: {data['timestamp']}")
    lines.append(END_MARKER)

    block = '\n'.join(lines)

    if BEGIN_MARKER in content and END_MARKER in content:
        pattern = re.escape(BEGIN_MARKER) + r'.*?' + re.escape(END_MARKER)
        content = re.sub(pattern, block, content, flags=re.DOTALL)
    else:
        content = content.rstrip() + '\n\n' + block + '\n'

    with open(AUDIT_SUMMARY, 'w', encoding='utf-8') as f:
        f.write(content)


def main() -> int:
    os.makedirs(REPORTS, exist_ok=True)

    outcomes = _load_json(OUTCOMES_JSON, [])
    if not isinstance(outcomes, list):
        outcomes = []

    coeff_series, ghs_deltas, msi_deltas = _extract_series(outcomes)

    # Compute Δc series
    delta_coeffs = _compute_deltas(coeff_series)
    samples = len(ghs_deltas)

    # Gather performance combined metric aligned with Δc length (one less than coeff_series)
    # Combined metric uses ghs_deltas[1:] etc? Actually each delta_coeff entry corresponds to transition between snapshot i-1 and i.
    # We'll align by skipping first performance delta to keep lengths consistent.
    if coeff_series and samples > 1:
        # For simplicity we align deltas length to delta_coeffs length
        combined_perf = []
        # Use ghs_deltas[1:] and msi_deltas[1:] to align with transitions
        for g, m in zip(ghs_deltas[1:], msi_deltas[1:]):
            combined_perf.append(g + (m / 2.0))
    else:
        combined_perf = []

    usable = len(combined_perf)  # number of transitions

    influences_raw: Dict[str, float] = {k: 0.0 for k in COEFF_KEYS}

    if usable >= MIN_SAMPLES:
        for k in COEFF_KEYS:
            changes = delta_coeffs[k]
            # Ensure alignment
            if len(changes) != usable:
                # Trim or pad
                if len(changes) > usable:
                    changes = changes[-usable:]
                else:
                    changes = changes + [0.0] * (usable - len(changes))
            var_c = _variance(changes)
            if var_c <= 0:
                influences_raw[k] = 0.0
            else:
                cov_c = _covariance(changes, combined_perf)
                influences_raw[k] = cov_c / var_c
    else:
        # Not enough data; keep zeros
        pass

    normalized = _normalize(influences_raw)
    # Build labels mapping explicitly to avoid comprehension analysis issues
    labels = {}
    for _k, _val in normalized.items():
        labels[_k] = _label(_val)

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'

    confidence = _confidence(usable)

    output = {
        'timestamp': timestamp,
        'usable_samples': usable,
        'raw_influence': influences_raw,
        'normalized_influence': normalized,
        'labels': labels,
        'confidence': confidence,
        'note': 'neutral due to insufficient data' if usable < MIN_SAMPLES else 'computed'
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)

    _update_audit_summary(output)

    print(json.dumps({
        'status': 'ok',
        'usable_samples': usable,
        'confidence': confidence,
        'note': output['note']
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
