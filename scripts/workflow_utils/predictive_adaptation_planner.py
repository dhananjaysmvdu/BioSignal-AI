#!/usr/bin/env python3
"""Predictive adaptation planner using historical outcome data.

Builds a simple linear regression model from adaptation history to forecast
the likely impact (GHS Δ, MSI Δ) of current coefficient configuration.

Enables proactive governance by simulating outcomes before applying changes.

Features → Targets:
  [confidence_weight, drift_weight, human_feedback_weight] → [ghs_delta, msi_delta]

Uses pure-Python least-squares regression (no numpy/scikit-learn dependencies).

Inputs:
  - logs/adaptation_outcomes.json: historical coefficients and their deltas
  - configs/governance_policy.json: current coefficients to predict for

Outputs:
  - reports/predicted_adaptation.json: forecast with expected deltas and outcome
  - reports/audit_summary.md: idempotent marker-based update
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
LOGS = os.path.join(ROOT, 'logs')

OUTCOMES_JSON = os.path.join(LOGS, 'adaptation_outcomes.json')
POLICY_JSON = os.path.join(CONFIGS, 'governance_policy.json')
PREDICTED_JSON = os.path.join(REPORTS, 'predicted_adaptation.json')
AUDIT_SUMMARY = os.path.join(REPORTS, 'audit_summary.md')

BEGIN_MARKER = '<!-- PREDICTIVE_ADAPTATION:BEGIN -->'
END_MARKER = '<!-- PREDICTIVE_ADAPTATION:END -->'

MIN_HISTORY = 5  # Minimum records needed for reliable prediction


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def _extract_training_data(outcomes: List[Dict[str, Any]]) -> Tuple[List[List[float]], List[float], List[float]]:
    """
    Extract features (coefficients) and targets (deltas) from outcomes.
    
    Returns: (X, y_ghs, y_msi)
      X: list of [conf, drift, human] coefficient vectors
      y_ghs: list of ghs_delta values
      y_msi: list of msi_delta values
    """
    X = []
    y_ghs = []
    y_msi = []
    
    for outcome in outcomes:
        # Skip first-run entries without meaningful deltas
        if outcome.get('note') == 'first evaluation, no prior baseline':
            continue
        
        coeffs = outcome.get('current_coefficients', {})
        ghs_delta = outcome.get('ghs_delta')
        msi_delta = outcome.get('msi_delta')
        
        if coeffs and ghs_delta is not None and msi_delta is not None:
            conf = float(coeffs.get('confidence_weight', 0.0))
            drift = float(coeffs.get('drift_weight', 0.0))
            human = float(coeffs.get('human_feedback_weight', 0.0))
            
            X.append([conf, drift, human])
            y_ghs.append(float(ghs_delta))
            y_msi.append(float(msi_delta))
    
    return X, y_ghs, y_msi


def _fit_linear_regression(X: List[List[float]], y: List[float]) -> Optional[List[float]]:
    """
    Fit linear regression using least-squares (pure Python).
    
    Model: y = β₀ + β₁*x₁ + β₂*x₂ + β₃*x₃
    
    Solves: (X^T X) β = X^T y
    
    Returns: [β₀, β₁, β₂, β₃] or None if insufficient data
    """
    if len(X) < 2 or len(y) < 2:
        return None
    
    n = len(X)
    k = len(X[0])  # number of features
    
    # Add intercept column (ones)
    X_aug = [[1.0] + row for row in X]
    
    # Compute X^T X
    XtX = [[0.0] * (k + 1) for _ in range(k + 1)]
    for i in range(k + 1):
        for j in range(k + 1):
            for row in X_aug:
                XtX[i][j] += row[i] * row[j]
    
    # Compute X^T y
    Xty = [0.0] * (k + 1)
    for i in range(k + 1):
        for row, y_val in zip(X_aug, y):
            Xty[i] += row[i] * y_val
    
    # Solve using Gaussian elimination
    try:
        beta = _solve_linear_system(XtX, Xty)
        return beta
    except Exception:
        return None


def _solve_linear_system(A: List[List[float]], b: List[float]) -> List[float]:
    """
    Solve Ax = b using Gaussian elimination with partial pivoting.
    """
    n = len(b)
    # Create augmented matrix
    M = [A[i][:] + [b[i]] for i in range(n)]
    
    # Forward elimination
    for i in range(n):
        # Partial pivoting
        max_row = i
        for k in range(i + 1, n):
            if abs(M[k][i]) > abs(M[max_row][i]):
                max_row = k
        M[i], M[max_row] = M[max_row], M[i]
        
        # Check for singular matrix
        if abs(M[i][i]) < 1e-10:
            raise ValueError("Singular matrix")
        
        # Eliminate column
        for k in range(i + 1, n):
            factor = M[k][i] / M[i][i]
            for j in range(i, n + 1):
                M[k][j] -= factor * M[i][j]
    
    # Back substitution
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = M[i][n]
        for j in range(i + 1, n):
            x[i] -= M[i][j] * x[j]
        x[i] /= M[i][i]
    
    return x


def _predict(beta: List[float], features: List[float]) -> float:
    """
    Make prediction: y = β₀ + β₁*x₁ + β₂*x₂ + β₃*x₃
    """
    result = beta[0]  # intercept
    for i, feat in enumerate(features):
        result += beta[i + 1] * feat
    return result


def _classify_expected_outcome(ghs_pred: float, msi_pred: float) -> str:
    """
    Classify predicted outcome based on expected deltas.
    """
    if ghs_pred > 0 and msi_pred > 0:
        return 'improve'
    elif ghs_pred < 0 or msi_pred < 0:
        return 'regress'
    else:
        return 'neutral'


def _update_audit_summary(
    ghs_pred: float,
    msi_pred: float,
    outcome: str,
    timestamp: str,
    reliable: bool = True
):
    if not os.path.exists(AUDIT_SUMMARY):
        return
    with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if not reliable:
        block = f"""{BEGIN_MARKER}
## Predictive Forecast

**Status:** Unreliable (insufficient historical data)  
**Forecast:** Neutral deltas predicted  
**Timestamp:** {timestamp}
{END_MARKER}"""
    else:
        block = f"""{BEGIN_MARKER}
## Predictive Forecast

**Expected GHS Δ:** {ghs_pred:+.1f}%  
**Expected MSI Δ:** {msi_pred:+.1f}%  
**Projected Outcome:** {outcome.capitalize()}  
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
    os.makedirs(REPORTS, exist_ok=True)
    
    # Load outcomes history
    outcomes = _load_json(OUTCOMES_JSON, [])
    if not isinstance(outcomes, list):
        outcomes = []
    
    # Load current policy
    policy = _load_json(POLICY_JSON, {})
    current_coeffs = policy.get('learning_coefficients', {})
    if not current_coeffs:
        current_coeffs = {
            'confidence_weight': 0.75,
            'drift_weight': 0.5,
            'human_feedback_weight': 0.5
        }
    
    current_features = [
        float(current_coeffs.get('confidence_weight', 0.75)),
        float(current_coeffs.get('drift_weight', 0.5)),
        float(current_coeffs.get('human_feedback_weight', 0.5))
    ]
    
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', '') + 'Z'
    
    # Extract training data
    X, y_ghs, y_msi = _extract_training_data(outcomes)
    
    # Check if sufficient history
    if len(X) < MIN_HISTORY:
        # Insufficient data: predict neutral
        prediction = {
            'timestamp': ts,
            'predicted_deltas': {'ghs': 0.0, 'msi': 0.0},
            'expected_outcome': 'neutral',
            'reliable': False,
            'note': f'insufficient history ({len(X)}/{MIN_HISTORY} records)'
        }
        
        with open(PREDICTED_JSON, 'w', encoding='utf-8') as f:
            json.dump(prediction, f, indent=2)
        
        _update_audit_summary(0.0, 0.0, 'neutral', ts, reliable=False)
        
        print(json.dumps({
            'status': 'unreliable',
            'predicted_outcome': 'neutral',
            'training_samples': len(X)
        }))
        return 0
    
    # Fit regression models
    beta_ghs = _fit_linear_regression(X, y_ghs)
    beta_msi = _fit_linear_regression(X, y_msi)
    
    if not beta_ghs or not beta_msi:
        # Model fitting failed
        prediction = {
            'timestamp': ts,
            'predicted_deltas': {'ghs': 0.0, 'msi': 0.0},
            'expected_outcome': 'neutral',
            'reliable': False,
            'note': 'model fitting failed'
        }
        
        with open(PREDICTED_JSON, 'w', encoding='utf-8') as f:
            json.dump(prediction, f, indent=2)
        
        _update_audit_summary(0.0, 0.0, 'neutral', ts, reliable=False)
        
        print(json.dumps({
            'status': 'unreliable',
            'predicted_outcome': 'neutral',
            'reason': 'model_fitting_failed'
        }))
        return 0
    
    # Make predictions
    ghs_pred = _predict(beta_ghs, current_features)
    msi_pred = _predict(beta_msi, current_features)
    
    # Classify outcome
    outcome = _classify_expected_outcome(ghs_pred, msi_pred)
    
    # Build prediction record
    prediction = {
        'timestamp': ts,
        'predicted_deltas': {
            'ghs': round(ghs_pred, 2),
            'msi': round(msi_pred, 2)
        },
        'expected_outcome': outcome,
        'reliable': True,
        'training_samples': len(X),
        'model_coefficients': {
            'ghs_model': [round(b, 4) for b in beta_ghs],
            'msi_model': [round(b, 4) for b in beta_msi]
        },
        'input_features': {
            'confidence_weight': current_features[0],
            'drift_weight': current_features[1],
            'human_feedback_weight': current_features[2]
        }
    }
    
    # Write prediction
    with open(PREDICTED_JSON, 'w', encoding='utf-8') as f:
        json.dump(prediction, f, indent=2)
    
    # Update audit summary
    _update_audit_summary(ghs_pred, msi_pred, outcome, ts, reliable=True)
    
    # Output summary
    print(json.dumps({
        'status': 'reliable',
        'predicted_outcome': outcome,
        'ghs_delta': round(ghs_pred, 2),
        'msi_delta': round(msi_pred, 2),
        'training_samples': len(X)
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
