#!/usr/bin/env python3
"""
Governance Reflex Learning Model (GRLM)
=========================================
Train a lightweight predictive model to forecast Reflex Effectiveness Index (REI)
from system context, enabling anticipatory policy adjustments.

Features:
- [RSI_prev, RSI_delta, GHS_prev, learning_rate_factor, audit_freq, policy_mode_encoded]
- Uses LinearRegression when ≥10 samples; weighted averages otherwise
- Outputs model coefficients, R², and predictions to JSON
- Updates audit summary with REFLEX_LEARNING marker

Author: BioSignal-AI Team
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from sklearn.linear_model import Ridge
    from sklearn.metrics import r2_score, mean_absolute_error
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️  scikit-learn not available, using fallback weighted averages", file=sys.stderr)


def load_json(path: Path) -> Dict[str, Any]:
    """Load JSON file with error handling."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️  Failed to load {path}: {e}", file=sys.stderr)
        return {}


def write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def append_history(path: Path, entry: Dict[str, Any], keep_last: int = 50) -> List[Dict[str, Any]]:
    """Append an entry to a JSON list file, keeping only last N entries.

    Returns the updated list.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data: List[Dict[str, Any]] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []
    data.append(entry)
    data = data[-keep_last:]
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)
    return data


def encode_policy_mode(mode: str) -> int:
    """Encode policy mode as integer."""
    modes = {
        "Critical Intervention": 0,
        "Caution Mode": 1,
        "Normal Operation": 2
    }
    return modes.get(mode, 1)  # Default to Caution Mode


def extract_features_and_targets(
    actions: List[Dict[str, Any]],
    evaluations: Dict[str, Any],
    history: Dict[str, Any],
    health: Dict[str, Any]
) -> Tuple[List[List[float]], List[float], List[str]]:
    """
    Extract feature matrix and target REI values from historical data.
    
    Returns:
        features: List of feature vectors
        targets: List of REI values
        timestamps: List of timestamps for each sample
    """
    features = []
    targets = []
    timestamps = []
    
    rsi_history = history.get("rsi", [])
    if not rsi_history:
        return [], [], []
    
    # Build RSI lookup
    rsi_by_time = {entry["timestamp"]: entry["value"] for entry in rsi_history}
    
    # Process each action that has an evaluation
    for i, action in enumerate(actions):
        timestamp = action.get("timestamp")
        if not timestamp:
            continue
        
        # Get REI for this action (from next evaluation or current)
        rei = action.get("rei", 0.0)
        
        # Get RSI at this time
        rsi_current = action.get("rsi", 100.0)
        
        # Get previous RSI (if available)
        rsi_prev = rsi_history[i-1]["value"] if i > 0 and i-1 < len(rsi_history) else rsi_current
        rsi_delta = rsi_current - rsi_prev
        
        # Get GHS (default to 0 if not available)
        ghs_prev = action.get("ghs", 0.0)
        
        # Get policy parameters
        learning_rate_factor = action.get("learning_rate_factor", 1.0)
        audit_freq = action.get("audit_frequency_days", 7)
        policy_mode = action.get("mode", "Normal Operation")
        policy_mode_encoded = encode_policy_mode(policy_mode)
        
        # Build feature vector
        feature_vec = [
            rsi_prev,
            rsi_delta,
            ghs_prev,
            learning_rate_factor,
            float(audit_freq),
            float(policy_mode_encoded)
        ]
        
        features.append(feature_vec)
        targets.append(rei)
        timestamps.append(timestamp)
    
    return features, targets, timestamps


def train_model_sklearn(
    features: List[List[float]],
    targets: List[float]
) -> Dict[str, Any]:
    """Train Ridge regression model using scikit-learn."""
    if not SKLEARN_AVAILABLE:
        raise RuntimeError("scikit-learn not available")
    
    X = np.array(features)
    y = np.array(targets)
    
    # Train Ridge regression (alpha=1.0 for slight regularization)
    model = Ridge(alpha=1.0)
    model.fit(X, y)
    
    # Make predictions
    y_pred = model.predict(X)
    
    # Calculate metrics
    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)
    
    # Extract coefficients
    feature_names = [
        "rsi_prev",
        "rsi_delta",
        "ghs_prev",
        "learning_rate_factor",
        "audit_freq",
        "policy_mode"
    ]
    
    coefficients = {
        name: float(coef)
        for name, coef in zip(feature_names, model.coef_)
    }
    
    return {
        "method": "Ridge",
        "coefficients": coefficients,
        "intercept": float(model.intercept_),
        "r2": float(r2),
        "mae": float(mae),
        "n_samples": len(targets)
    }


def train_model_fallback(
    features: List[List[float]],
    targets: List[float]
) -> Dict[str, Any]:
    """Fallback to weighted averages when scikit-learn unavailable."""
    n_samples = len(targets)
    
    if n_samples == 0:
        return {
            "method": "WeightedAverage",
            "coefficients": {},
            "intercept": 0.0,
            "r2": 0.0,
            "mae": 0.0,
            "n_samples": 0
        }
    
    # Calculate mean REI
    mean_rei = sum(targets) / n_samples
    
    # Calculate simple feature correlations (as proxy for coefficients)
    feature_names = [
        "rsi_prev",
        "rsi_delta",
        "ghs_prev",
        "learning_rate_factor",
        "audit_freq",
        "policy_mode"
    ]
    
    coefficients = {}
    for i, name in enumerate(feature_names):
        feature_values = [f[i] for f in features]
        # Simple correlation: cov(x, y) / var(x)
        mean_feature = sum(feature_values) / n_samples
        cov = sum((f - mean_feature) * (t - mean_rei) for f, t in zip(feature_values, targets)) / n_samples
        var = sum((f - mean_feature) ** 2 for f in feature_values) / n_samples
        coefficients[name] = cov / var if var > 0 else 0.0
    
    # Calculate R² with mean prediction
    ss_res = sum((t - mean_rei) ** 2 for t in targets)
    ss_tot = sum((t - mean_rei) ** 2 for t in targets)
    r2 = 0.0  # Baseline model has R²=0
    
    mae = sum(abs(t - mean_rei) for t in targets) / n_samples
    
    return {
        "method": "WeightedAverage",
        "coefficients": coefficients,
        "intercept": mean_rei,
        "r2": r2,
        "mae": mae,
        "n_samples": n_samples
    }


def predict_rei(
    model_data: Dict[str, Any],
    feature_vec: List[float]
) -> float:
    """Predict REI using trained model."""
    coefficients = model_data.get("coefficients", {})
    intercept = model_data.get("intercept", 0.0)
    
    feature_names = [
        "rsi_prev",
        "rsi_delta",
        "ghs_prev",
        "learning_rate_factor",
        "audit_freq",
        "policy_mode"
    ]
    
    # Linear prediction
    prediction = intercept
    for name, value in zip(feature_names, feature_vec):
        coef = coefficients.get(name, 0.0)
        prediction += coef * value
    
    return prediction


def get_top_feature(coefficients: Dict[str, float]) -> Tuple[str, float]:
    """Get feature with highest absolute coefficient."""
    if not coefficients:
        return "none", 0.0
    
    abs_coefs = {name: abs(coef) for name, coef in coefficients.items()}
    top_name = max(abs_coefs, key=abs_coefs.get)
    return top_name, coefficients[top_name]


def update_audit_summary(
    audit_path: Path,
    model_data: Dict[str, Any]
) -> None:
    """Update audit summary with REFLEX_LEARNING marker."""
    n_samples = model_data.get("n_samples", 0)
    r2 = model_data.get("r2", 0.0)
    coefficients = model_data.get("coefficients", {})
    
    top_feature, top_coef = get_top_feature(coefficients)
    
    # Format message
    if n_samples < 10:
        message = f"Reflex Learning Model: insufficient data (n={n_samples}), using baseline prediction."
    else:
        message = (
            f"Reflex Learning Model: trained on {n_samples} samples, "
            f"R²={r2:.2f}, top feature: {top_feature} ({top_coef:+.2f})"
        )
    
    marker_begin = "<!-- REFLEX_LEARNING:BEGIN -->"
    marker_end = "<!-- REFLEX_LEARNING:END -->"
    block = f"{marker_begin}\n{message}\n{marker_end}\n"
    
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    
    if audit_path.exists():
        content = audit_path.read_text(encoding='utf-8')
        pattern = re.compile(
            r"<!-- REFLEX_LEARNING:BEGIN -->.*?<!-- REFLEX_LEARNING:END -->\n?",
            re.DOTALL
        )
        
        if pattern.search(content):
            # Replace existing block
            content = pattern.sub(block, content)
        else:
            # Append new block
            content += f"\n{block}"
        
        # Atomic write
        tmp = audit_path.with_suffix('.tmp')
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(audit_path)
    else:
        # Create new file
        audit_path.write_text(block, encoding='utf-8')


def main(argv: List[str] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Train governance reflex learning model"
    )
    parser.add_argument(
        "--actions-log",
        type=Path,
        default=Path("logs/regime_policy_actions.json"),
        help="Path to regime policy actions log"
    )
    parser.add_argument(
        "--reflex",
        type=Path,
        default=Path("reports/reflex_evaluation.json"),
        help="Path to reflex evaluation JSON"
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=Path("logs/regime_stability_history.json"),
        help="Path to regime stability history JSON"
    )
    parser.add_argument(
        "--health",
        type=Path,
        default=Path("reports/governance_health.json"),
        help="Path to governance health JSON"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/reflex_learning_model.json"),
        help="Path to output model JSON"
    )
    parser.add_argument(
        "--audit-summary",
        type=Path,
        default=Path("reports/audit_summary.md"),
        help="Path to audit summary markdown"
    )
    parser.add_argument(
        "--history-output",
        type=Path,
        default=Path("logs/reflex_model_history.json"),
        help="Path to model training history JSON list"
    )
    
    args = parser.parse_args(argv)
    
    # Load data
    actions = load_json(args.actions_log)
    if isinstance(actions, list):
        actions_list = actions
    else:
        actions_list = []
    
    evaluations = load_json(args.reflex)
    history = load_json(args.history)
    health = load_json(args.health)
    
    # Extract features and targets
    features, targets, timestamps = extract_features_and_targets(
        actions_list,
        evaluations,
        history,
        health
    )
    
    # Train model
    if len(features) >= 10 and SKLEARN_AVAILABLE:
        model_data = train_model_sklearn(features, targets)
    else:
        model_data = train_model_fallback(features, targets)
    
    # Add metadata
    now_iso = datetime.now(UTC).isoformat()
    model_data["last_train_time"] = now_iso
    model_data["sklearn_available"] = SKLEARN_AVAILABLE
    # Backward/compat key expected by tests
    model_data["r2_score"] = model_data.get("r2", 0.0)
    
    # Predict next REI (using most recent features if available)
    if features:
        predicted_rei = predict_rei(model_data, features[-1])
        model_data["last_predicted_rei"] = float(predicted_rei)
    else:
        model_data["last_predicted_rei"] = 0.0

    # Summarize coefficients (top 3 by absolute value)
    coefs = model_data.get("coefficients", {})
    coef_items = sorted(coefs.items(), key=lambda x: abs(x[1]), reverse=True)
    coef_summary = [f"{k}:{v:+.3f}" for k, v in coef_items[:3]]

    # Persist training history (last 50)
    top_feature, top_coef = get_top_feature(coefs)
    history_entry = {
        "timestamp": now_iso,
        "n_samples": model_data.get("n_samples", 0),
        "r2": model_data.get("r2", 0.0),
        "r2_score": model_data.get("r2", 0.0),
        "top_feature": top_feature,
        "top_coef": top_coef,
        "coefficients_summary": coef_summary,
        "mae": model_data.get("mae", 0.0)
    }
    history_list = append_history(args.history_output, history_entry, keep_last=50)

    # Rolling R2 trend (delta between last and previous avg of last 5)
    if len(history_list) >= 2:
        last_r2 = history_list[-1].get("r2", 0.0)
        prev_r2s = [h.get("r2", 0.0) for h in history_list[:-1][-5:]]
        prev_avg = sum(prev_r2s) / len(prev_r2s) if prev_r2s else 0.0
        model_data["rolling_r2_trend"] = last_r2 - prev_avg
    else:
        model_data["rolling_r2_trend"] = 0.0
    
    # Save model
    write_json(args.output, model_data)
    
    # Update audit summary
    update_audit_summary(args.audit_summary, model_data)
    
    # Output result
    result = {
        "status": "ok",
        "model": str(args.output),
        "n_samples": model_data["n_samples"],
        "r2": model_data["r2"],
        "r2_score": model_data.get("r2_score", model_data.get("r2", 0.0)),
        "mae": model_data["mae"],
        "method": model_data["method"],
        "predicted_rei": model_data["last_predicted_rei"],
        "history_path": str(args.history_output),
        "rolling_r2_trend": model_data.get("rolling_r2_trend", 0.0)
    }
    
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
