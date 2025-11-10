#!/usr/bin/env python3
"""
Reflex Predictive Overlay Dashboard
====================================
Visualize predicted vs actual REI to assess governance system's predictive accuracy.

Panels:
1. Scatter plot: Predicted vs Actual REI
2. Temporal alignment: Predicted + Actual REI trends
3. Model coefficients: Bar chart by feature weight

Author: BioSignal-AI Team
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


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


def encode_policy_mode(mode: str) -> int:
    """Encode policy mode as integer."""
    modes = {
        "Critical Intervention": 0,
        "Caution Mode": 1,
        "Normal Operation": 2
    }
    return modes.get(mode, 1)


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


def extract_predictions_and_actuals(
    actions: List[Dict[str, Any]],
    model_data: Dict[str, Any],
    history: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Extract predicted and actual REI values for each action.
    
    Returns:
        predictions: List of dicts with timestamp, predicted, actual, error
        mean_error: Mean absolute error
    """
    predictions = []
    rsi_history = history.get("rsi", [])
    
    if not rsi_history:
        return [], 0.0
    
    total_error = 0.0
    n_valid = 0
    
    for i, action in enumerate(actions):
        timestamp = action.get("timestamp")
        if not timestamp:
            continue
        
        # Get actual REI
        actual_rei = action.get("rei", 0.0)
        
        # Get RSI at this time
        rsi_current = action.get("rsi", 100.0)
        rsi_prev = rsi_history[i-1]["value"] if i > 0 and i-1 < len(rsi_history) else rsi_current
        rsi_delta = rsi_current - rsi_prev
        
        # Get GHS
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
        
        # Predict REI
        predicted_rei = predict_rei(model_data, feature_vec)
        
        # Calculate error
        error = abs(predicted_rei - actual_rei)
        total_error += error
        n_valid += 1
        
        predictions.append({
            "timestamp": timestamp,
            "predicted": round(predicted_rei, 2),
            "actual": round(actual_rei, 2),
            "error": round(error, 2),
            "mode": policy_mode
        })
    
    mean_error = total_error / n_valid if n_valid > 0 else 0.0
    
    return predictions, mean_error


def build_dashboard_html(
    predictions: List[Dict[str, Any]],
    model_data: Dict[str, Any],
    mean_error: float
) -> str:
    """Build HTML dashboard with three panels."""
    
    # Extract coefficients for bar chart
    coefficients = model_data.get("coefficients", {})
    coef_items = sorted(coefficients.items(), key=lambda x: abs(x[1]), reverse=True)
    
    r2 = model_data.get("r2", 0.0)
    n_samples = model_data.get("n_samples", 0)
    method = model_data.get("method", "Unknown")
    
    # Current status
    last_actual = predictions[-1]["actual"] if predictions else 0.0
    last_predicted = predictions[-1]["predicted"] if predictions else 0.0
    last_error = predictions[-1]["error"] if predictions else 0.0
    
    # Prepare data for JavaScript
    scatter_data = [
        {"predicted": p["predicted"], "actual": p["actual"], "mode": p["mode"]}
        for p in predictions
    ]
    
    temporal_data = [
        {"timestamp": p["timestamp"], "predicted": p["predicted"], "actual": p["actual"]}
        for p in predictions
    ]
    
    coef_data = [
        {"name": name, "value": value}
        for name, value in coef_items
    ]
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Reflex Predictive Performance</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 20px;
      background: #f5f5f5;
    }}
    h1 {{
      color: #2c3e50;
      border-bottom: 3px solid #3498db;
      padding-bottom: 10px;
    }}
    .status {{
      background: #ecf0f1;
      padding: 15px;
      border-radius: 8px;
      margin: 20px 0;
      border-left: 4px solid #3498db;
    }}
    .panel {{
      background: white;
      padding: 20px;
      margin: 20px 0;
      border-radius: 8px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    h3 {{
      color: #34495e;
      margin-top: 0;
    }}
    canvas {{
      max-width: 100%;
      height: 400px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 15px;
      margin: 20px 0;
    }}
    .metric {{
      background: #3498db;
      color: white;
      padding: 15px;
      border-radius: 8px;
      text-align: center;
    }}
    .metric-value {{
      font-size: 24px;
      font-weight: bold;
    }}
    .metric-label {{
      font-size: 14px;
      opacity: 0.9;
    }}
  </style>
</head>
<body>
  <h1>🔮 Reflex Predictive Performance Dashboard</h1>
  
  <div class="status">
    <strong>Current Status:</strong> 
    Actual REI={last_actual:+.2f}, Predicted={last_predicted:+.2f}, Error={last_error:.2f}
  </div>
  
  <div class="metrics">
    <div class="metric">
      <div class="metric-value">{r2:.3f}</div>
      <div class="metric-label">R² Score</div>
    </div>
    <div class="metric">
      <div class="metric-value">{mean_error:.3f}</div>
      <div class="metric-label">Mean Abs Error</div>
    </div>
    <div class="metric">
      <div class="metric-value">{n_samples}</div>
      <div class="metric-label">Training Samples</div>
    </div>
    <div class="metric">
      <div class="metric-value">{method}</div>
      <div class="metric-label">Model Type</div>
    </div>
  </div>
  
  <div class="panel">
    <h3>📊 Panel 1: Predicted vs Actual REI (Scatter)</h3>
    <canvas id="scatterChart"></canvas>
  </div>
  
  <div class="panel">
    <h3>📈 Panel 2: Temporal Alignment (Predicted + Actual Trends)</h3>
    <canvas id="temporalChart"></canvas>
  </div>
  
  <div class="panel">
    <h3>📐 Panel 3: Model Coefficients (Feature Importance)</h3>
    <canvas id="coefChart"></canvas>
  </div>
  
  <script>
  (function() {{
    const scatterData = {json.dumps(scatter_data)};
    const temporalData = {json.dumps(temporal_data)};
    const coefData = {json.dumps(coef_data)};
    
    // Panel 1: Scatter Plot
    function drawScatter(canvasId) {{
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext('2d');
      const width = canvas.width = canvas.offsetWidth;
      const height = canvas.height = 400;
      
      ctx.clearRect(0, 0, width, height);
      
      if (scatterData.length === 0) {{
        ctx.fillStyle = '#7f8c8d';
        ctx.font = '16px sans-serif';
        ctx.fillText('No data available', width/2 - 60, height/2);
        return;
      }}
      
      // Calculate bounds
      const allValues = scatterData.flatMap(d => [d.predicted, d.actual]);
      const minVal = Math.min(...allValues, -5);
      const maxVal = Math.max(...allValues, 5);
      const range = maxVal - minVal;
      
      const padding = 60;
      const plotWidth = width - 2 * padding;
      const plotHeight = height - 2 * padding;
      
      // Scale functions
      const scaleX = (val) => padding + ((val - minVal) / range) * plotWidth;
      const scaleY = (val) => height - padding - ((val - minVal) / range) * plotHeight;
      
      // Draw axes
      ctx.strokeStyle = '#bdc3c7';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padding, height - padding);
      ctx.lineTo(width - padding, height - padding);
      ctx.moveTo(padding, padding);
      ctx.lineTo(padding, height - padding);
      ctx.stroke();
      
      // Draw diagonal (perfect prediction line)
      ctx.strokeStyle = '#e74c3c';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.moveTo(scaleX(minVal), scaleY(minVal));
      ctx.lineTo(scaleX(maxVal), scaleY(maxVal));
      ctx.stroke();
      ctx.setLineDash([]);
      
      // Draw points
      scatterData.forEach(d => {{
        const x = scaleX(d.predicted);
        const y = scaleY(d.actual);
        
        // Color by mode
        if (d.mode === "Critical Intervention") {{
          ctx.fillStyle = '#e74c3c';
        }} else if (d.mode === "Caution Mode") {{
          ctx.fillStyle = '#f39c12';
        }} else {{
          ctx.fillStyle = '#27ae60';
        }}
        
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, 2 * Math.PI);
        ctx.fill();
      }});
      
      // Labels
      ctx.fillStyle = '#2c3e50';
      ctx.font = '14px sans-serif';
      ctx.fillText('Predicted REI →', width/2 - 50, height - 20);
      ctx.save();
      ctx.translate(20, height/2 + 50);
      ctx.rotate(-Math.PI/2);
      ctx.fillText('Actual REI →', 0, 0);
      ctx.restore();
    }}
    
    // Panel 2: Temporal Chart
    function drawTemporal(canvasId) {{
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext('2d');
      const width = canvas.width = canvas.offsetWidth;
      const height = canvas.height = 400;
      
      ctx.clearRect(0, 0, width, height);
      
      if (temporalData.length === 0) {{
        ctx.fillStyle = '#7f8c8d';
        ctx.font = '16px sans-serif';
        ctx.fillText('No data available', width/2 - 60, height/2);
        return;
      }}
      
      // Calculate bounds
      const allREI = temporalData.flatMap(d => [d.predicted, d.actual]);
      const minREI = Math.min(...allREI, -5);
      const maxREI = Math.max(...allREI, 5);
      const rangeREI = maxREI - minREI;
      
      const padding = 60;
      const plotWidth = width - 2 * padding;
      const plotHeight = height - 2 * padding;
      
      // Scale functions
      const scaleX = (index) => padding + (index / (temporalData.length - 1)) * plotWidth;
      const scaleY = (val) => height - padding - ((val - minREI) / rangeREI) * plotHeight;
      
      // Draw axes
      ctx.strokeStyle = '#bdc3c7';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padding, height - padding);
      ctx.lineTo(width - padding, height - padding);
      ctx.moveTo(padding, padding);
      ctx.lineTo(padding, height - padding);
      ctx.stroke();
      
      // Draw zero line
      if (minREI < 0 && maxREI > 0) {{
        const y0 = scaleY(0);
        ctx.strokeStyle = '#95a5a6';
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(padding, y0);
        ctx.lineTo(width - padding, y0);
        ctx.stroke();
        ctx.setLineDash([]);
      }}
      
      // Draw predicted line
      ctx.strokeStyle = '#3498db';
      ctx.lineWidth = 2;
      ctx.beginPath();
      temporalData.forEach((d, i) => {{
        const x = scaleX(i);
        const y = scaleY(d.predicted);
        if (i === 0) {{
          ctx.moveTo(x, y);
        }} else {{
          ctx.lineTo(x, y);
        }}
      }});
      ctx.stroke();
      
      // Draw actual line
      ctx.strokeStyle = '#e74c3c';
      ctx.lineWidth = 2;
      ctx.beginPath();
      temporalData.forEach((d, i) => {{
        const x = scaleX(i);
        const y = scaleY(d.actual);
        if (i === 0) {{
          ctx.moveTo(x, y);
        }} else {{
          ctx.lineTo(x, y);
        }}
      }});
      ctx.stroke();
      
      // Legend
      ctx.fillStyle = '#3498db';
      ctx.fillRect(width - 180, 20, 20, 10);
      ctx.fillStyle = '#2c3e50';
      ctx.font = '12px sans-serif';
      ctx.fillText('Predicted', width - 155, 30);
      
      ctx.fillStyle = '#e74c3c';
      ctx.fillRect(width - 180, 40, 20, 10);
      ctx.fillStyle = '#2c3e50';
      ctx.fillText('Actual', width - 155, 50);
      
      // Labels
      ctx.fillStyle = '#2c3e50';
      ctx.font = '14px sans-serif';
      ctx.fillText('Time →', width/2 - 30, height - 20);
      ctx.save();
      ctx.translate(20, height/2 + 20);
      ctx.rotate(-Math.PI/2);
      ctx.fillText('REI →', 0, 0);
      ctx.restore();
    }}
    
    // Panel 3: Coefficient Bar Chart
    function drawCoef(canvasId) {{
      const canvas = document.getElementById(canvasId);
      const ctx = canvas.getContext('2d');
      const width = canvas.width = canvas.offsetWidth;
      const height = canvas.height = 400;
      
      ctx.clearRect(0, 0, width, height);
      
      if (coefData.length === 0) {{
        ctx.fillStyle = '#7f8c8d';
        ctx.font = '16px sans-serif';
        ctx.fillText('No coefficients available', width/2 - 80, height/2);
        return;
      }}
      
      const padding = 60;
      const plotHeight = height - 2 * padding;
      const barHeight = plotHeight / coefData.length - 10;
      
      // Calculate max coefficient for scaling
      const maxCoef = Math.max(...coefData.map(d => Math.abs(d.value)));
      
      coefData.forEach((d, i) => {{
        const y = padding + i * (barHeight + 10);
        const barWidth = (Math.abs(d.value) / maxCoef) * (width - 2 * padding - 150);
        const x = d.value >= 0 ? width/2 : width/2 - barWidth;
        
        // Draw bar
        ctx.fillStyle = d.value >= 0 ? '#27ae60' : '#e74c3c';
        ctx.fillRect(x, y, barWidth, barHeight);
        
        // Draw label
        ctx.fillStyle = '#2c3e50';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(d.name, width/2 - 10, y + barHeight/2 + 4);
        
        // Draw value
        ctx.textAlign = 'left';
        ctx.fillText(d.value.toFixed(3), width/2 + barWidth + 10, y + barHeight/2 + 4);
      }});
      
      // Draw zero line
      ctx.strokeStyle = '#34495e';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(width/2, padding);
      ctx.lineTo(width/2, height - padding);
      ctx.stroke();
      
      ctx.textAlign = 'left';
    }}
    
    // Draw all charts
    drawScatter('scatterChart');
    drawTemporal('temporalChart');
    drawCoef('coefChart');
  }})();
  </script>
</body>
</html>
"""
    
    return html


def update_audit_summary(
    audit_path: Path,
    last_actual: float,
    last_predicted: float,
    error: float
) -> None:
    """Update audit summary with REFLEX_PREDICTION marker."""
    message = (
        f"Reflex Prediction: last actual REI={last_actual:+.2f}, "
        f"predicted={last_predicted:+.2f}, error={error:.2f}."
    )
    
    marker_begin = "<!-- REFLEX_PREDICTION:BEGIN -->"
    marker_end = "<!-- REFLEX_PREDICTION:END -->"
    block = f"{marker_begin}\n{message}\n{marker_end}\n"
    
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    
    if audit_path.exists():
        content = audit_path.read_text(encoding='utf-8')
        pattern = re.compile(
            r"<!-- REFLEX_PREDICTION:BEGIN -->.*?<!-- REFLEX_PREDICTION:END -->\n?",
            re.DOTALL
        )
        
        if pattern.search(content):
            content = pattern.sub(block, content)
        else:
            content += f"\n{block}"
        
        tmp = audit_path.with_suffix('.tmp')
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(audit_path)
    else:
        audit_path.write_text(block, encoding='utf-8')


def main(argv: List[str] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate reflex predictive performance dashboard"
    )
    parser.add_argument(
        "--actions-log",
        type=Path,
        default=Path("logs/regime_policy_actions.json"),
        help="Path to regime policy actions log"
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("reports/reflex_learning_model.json"),
        help="Path to reflex learning model JSON"
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=Path("logs/regime_stability_history.json"),
        help="Path to regime stability history JSON"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/reflex_predictive_dashboard.html"),
        help="Path to output dashboard HTML"
    )
    parser.add_argument(
        "--audit-summary",
        type=Path,
        default=Path("reports/audit_summary.md"),
        help="Path to audit summary markdown"
    )
    
    args = parser.parse_args(argv)
    
    # Load data
    actions = load_json(args.actions_log)
    if isinstance(actions, list):
        actions_list = actions
    else:
        actions_list = []
    
    model_data = load_json(args.model)
    history = load_json(args.history)
    
    # Extract predictions and actuals
    predictions, mean_error = extract_predictions_and_actuals(
        actions_list,
        model_data,
        history
    )
    
    # Build dashboard HTML
    html = build_dashboard_html(predictions, model_data, mean_error)
    
    # Write dashboard
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix('.tmp')
    tmp.write_text(html, encoding='utf-8')
    tmp.replace(args.output)
    
    # Update audit summary
    last_actual = predictions[-1]["actual"] if predictions else 0.0
    last_predicted = predictions[-1]["predicted"] if predictions else 0.0
    last_error = predictions[-1]["error"] if predictions else 0.0
    
    update_audit_summary(args.audit_summary, last_actual, last_predicted, last_error)
    
    # Output result
    result = {
        "status": "ok",
        "dashboard": str(args.output),
        "n_predictions": len(predictions),
        "mean_error": round(mean_error, 3),
        "r2": model_data.get("r2", 0.0),
        "last_actual": last_actual,
        "last_predicted": last_predicted
    }
    
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
