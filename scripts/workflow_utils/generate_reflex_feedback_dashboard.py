#!/usr/bin/env python3
"""
Generate Reflex Feedback Dashboard

Creates an interactive HTML visualization showing:
- REI trend line (color-coded by classification)
- RSI vs GHS dual-axis timeline
- Recent reflex decision timeline
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


AUDIT_MARKER_BEGIN = "<!-- REFLEX_FEEDBACK:BEGIN -->"
AUDIT_MARKER_END = "<!-- REFLEX_FEEDBACK:END -->"


def load_json(path: str, default: Any = None) -> Any:
    """Load JSON file with fallback default."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default
    except Exception:
        return default


def get_rei_color(classification: str) -> str:
    """Get color code for REI classification."""
    if classification == "Effective":
        return "#2cbe4e"  # green
    elif classification == "Counterproductive":
        return "#d73a49"  # red
    else:
        return "#dfb317"  # yellow


def get_classification_emoji(classification: str) -> str:
    """Get emoji for classification."""
    if classification == "Effective":
        return "Γ£à"
    elif classification == "Counterproductive":
        return "ΓÜá∩╕Å"
    else:
        return "Γ₧í∩╕Å"


def build_dashboard_html(
    rei_history: List[Dict[str, Any]],
    rsi_history: List[Dict[str, Any]],
    ghs_history: List[Dict[str, Any]],
    current_evaluation: Dict[str, Any],
    meta_performance: Dict[str, Any] = None,
    model_history: List[Dict[str, Any]] = None,
  forecast_alignment: Dict[str, Any] = None,
  forecast_consistency: Dict[str, Any] = None
) -> Tuple[str, float, Optional[Dict[str, Any]]]:
    """Build the complete HTML dashboard."""
    
    # Extract meta-performance data
    mpi = 0.0
    mpi_status = "Unknown"
    mpi_delta_r2 = 0.0
    mpi_drift = 0.0
    mpi_emoji = "ΓÜ¬"
    mpi_color = "#gray"
    
    if meta_performance:
        mpi = meta_performance.get("mpi", 0.0)
        mpi_status = meta_performance.get("classification", "Unknown")
        mpi_delta_r2 = meta_performance.get("delta_r2", 0.0)
        mpi_drift = meta_performance.get("error_drift", 0.0)
        
        if mpi >= 80:
            mpi_emoji = "≡ƒƒó"
            mpi_color = "#2cbe4e"
        elif mpi >= 60:
            mpi_emoji = "≡ƒƒí"
            mpi_color = "#dfb317"
        else:
            mpi_emoji = "≡ƒö┤"
            mpi_color = "#d73a49"

    # Compute stability score for forecast consistency gauge
    stability_score_value = None
    stability_color_value = "#2cbe4e"
    stability_label = "Forecast Consistent"
    stability_emoji = "🟢"
    consistency_status = "Predictive coupling status available."
    if isinstance(forecast_consistency, dict) and forecast_consistency:
        curr_corr = float(forecast_consistency.get("current_correlation", 0.0))
        delta_corr = float(forecast_consistency.get("delta_correlation", 0.0))
        delta_clamped = min(max(abs(delta_corr), 0.0), 1.0)
        base_score = max(0.0, 1.0 - delta_clamped)
        polarity_multiplier = 1.0 if curr_corr > 0 else 0.5
        stability_score_value = max(0.0, min(100.0, 100.0 * base_score * polarity_multiplier))

        if stability_score_value >= 80:
            stability_label = "Forecast Consistent"
            stability_color_value = "#2cbe4e"
            stability_emoji = "🟢"
        elif stability_score_value >= 60:
            stability_label = "Moderate Drift"
            stability_color_value = "#dfb317"
            stability_emoji = "🟡"
        else:
            stability_label = "Inconsistent Forecasts"
            stability_color_value = "#d73a49"
            stability_emoji = "🔴"

        consistency_status = forecast_consistency.get(
            "status",
            "Forecast coupling monitored; stability score derived from REI↔MPI dynamics.",
        )

        forecast_consistency["stability_score"] = stability_score_value
        forecast_consistency["stability_label"] = stability_label
        forecast_consistency["stability_color"] = stability_color_value
        forecast_consistency["stability_emoji"] = stability_emoji
        forecast_consistency.setdefault("current_correlation", curr_corr)
        forecast_consistency.setdefault("delta_correlation", delta_corr)
    else:
        forecast_consistency = {}

    consistency_panel = ""
    stability_snapshot = None
    if stability_score_value is not None:
        consistency_panel = f"""
      <!-- CONSISTENCY_GAUGE:BEGIN -->
      <div style=\"margin-top: 16px; display: flex; align-items: center; gap: 16px;\">
        <canvas id=\"consistencyGauge\" width=\"200\" height=\"120\"></canvas>
        <div>
          <p style=\"font-size: 16px; margin: 4px 0; color: {stability_color_value};\"><strong>Consistency:</strong> {stability_emoji} {stability_label}</p>
          <p style=\"margin: 4px 0;\"><strong>Stability Score:</strong> {stability_score_value:.1f}%</p>
          <p style=\"margin: 4px 0; font-size: 12px; color: #666;\">Measures coherence of predictive coupling (REI↔MPI).</p>
          <p style=\"margin: 4px 0; font-size: 12px; color: #999;\">{consistency_status}</p>
        </div>
      </div>
      <!-- CONSISTENCY_GAUGE:END -->
"""
        stability_snapshot = {
            "score": stability_score_value,
            "label": stability_label,
            "emoji": stability_emoji,
            "color": stability_color_value,
            "status": consistency_status,
        }
    stability_score_for_js = float(stability_score_value) if stability_score_value is not None else 0.0

    standalone_consistency_panel = ""
    if consistency_panel and not meta_performance:
        standalone_consistency_panel = f"""
    <section id="forecast_consistency" style="background: {stability_color_value}22; padding: 16px; border-radius: 8px; border-left: 4px solid {stability_color_value}; margin-bottom: 24px;">
      <h3 style="margin-top: 0;">Forecast Consistency Monitor</h3>
{consistency_panel}
    </section>
    """

    # Extract MPI trend from model history (last 10 runs)
    mpi_trend_values = []
    mpi_trend_labels = []
    mpi_trend_direction = "ΓåÆ steady"
    if model_history:
        # Get last 10 entries
        recent_history = model_history[-10:] if len(model_history) > 10 else model_history
        for entry in recent_history:
            # Try to get r2_score, fallback to r2
            r2 = entry.get("r2_score", entry.get("r2", 0.0))
            mae = entry.get("mae", 0.0)
            
            # Approximate MPI from R┬▓ (simple heuristic if MPI not stored)
            # MPI Γëê R┬▓ * 100 (rough estimate when historical MPI not available)
            estimated_mpi = r2 * 100 if r2 else 0.0
            mpi_trend_values.append(estimated_mpi)
            
            # Extract timestamp label
            ts = entry.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                label = dt.strftime("%m-%d")
            except Exception:
                label = ts[:10] if ts else "N/A"
            mpi_trend_labels.append(label)
        
        # Calculate trend direction
        if len(mpi_trend_values) >= 2:
            mid = len(mpi_trend_values) // 2
            first_half_avg = sum(mpi_trend_values[:mid]) / mid if mid > 0 else 0
            second_half_avg = sum(mpi_trend_values[mid:]) / (len(mpi_trend_values) - mid)
            delta = second_half_avg - first_half_avg
            if delta > 5:
                mpi_trend_direction = "Γåæ improving"
            elif delta < -5:
                mpi_trend_direction = "Γåô degrading"
    
    # Compute MPI forecast using least squares linear regression
    mpi_forecast_values = []
    mpi_forecast_slope = 0.0
    if len(mpi_trend_values) >= 3:
        n = len(mpi_trend_values)
        x = list(range(n))
        y = mpi_trend_values
        
        # Least squares: slope = (n*╬úxy - ╬úx*╬úy) / (n*╬úx┬▓ - (╬úx)┬▓)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(xi ** 2 for xi in x)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2) if (n * sum_x2 - sum_x ** 2) != 0 else 0
        intercept = (sum_y - slope * sum_x) / n
        
        mpi_forecast_slope = slope
        
        # Project 5 cycles ahead
        last_value = y[-1]
        for i in range(1, 6):
            forecast_val = last_value + slope * i
            # Clamp forecast to [0, 150] range (MPI can theoretically exceed 100)
            forecast_val = max(0, min(forecast_val, 150))
            mpi_forecast_values.append(forecast_val)
    
    # Prepare data for JavaScript
    rei_labels = []
    rei_values = []
    rei_colors = []
    
    for entry in rei_history[-20:]:  # Last 20
        ts = entry.get("timestamp", "")
        # Parse and format timestamp
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            label = dt.strftime("%m-%d %H:%M")
        except Exception:
            label = ts[:16] if ts else "N/A"
        rei_labels.append(label)
        rei_values.append(float(entry.get("rei", 0.0)))
        rei_colors.append(get_rei_color(entry.get("classification", "Neutral")))
    
    # RSI timeline
    rsi_labels = []
    rsi_values = []
    for entry in rsi_history[-20:]:
        ts = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            label = dt.strftime("%m-%d %H:%M")
        except Exception:
            label = ts[:16] if ts else "N/A"
        rsi_labels.append(label)
        rsi_values.append(float(entry.get("value", 100.0)))
    
    # GHS timeline (aligned with RSI or separate)
    ghs_labels = []
    ghs_values = []
    for entry in ghs_history[-20:]:
        ts = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            label = dt.strftime("%m-%d %H:%M")
        except Exception:
            label = ts[:16] if ts else "N/A"
        ghs_labels.append(label)
        ghs_values.append(float(entry.get("ghs", 0.0)))
    
    # Recent decisions (last 10)
    decision_rows = ""
    for i, entry in enumerate(rei_history[-10:], 1):
        emoji = get_classification_emoji(entry.get("classification", "Neutral"))
        mode = entry.get("policy_mode", "N/A")
        rei = entry.get("rei", 0.0)
        classification = entry.get("classification", "Neutral")
        ts = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            time_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            time_str = ts[:19] if ts else "N/A"
        
        decision_rows += f"""
        <tr>
          <td>{i}</td>
          <td>{time_str}</td>
          <td>{mode}</td>
          <td style="text-align:right;">{rei:+.2f}</td>
          <td>{emoji} {classification}</td>
        </tr>
        """
    
    # Current status
    current_rei = current_evaluation.get("rei", 0.0)
    current_class = current_evaluation.get("classification", "Neutral")
    current_rsi = current_evaluation.get("current_rsi", 100.0)
    current_ghs = current_evaluation.get("current_ghs", 0.0)
    current_emoji = get_classification_emoji(current_class)
    
    # Build meta-performance status section
    meta_section = ""
    if meta_performance:
        # Add MPI trend chart if history available
        trend_chart = ""
        if mpi_trend_values:
            trend_chart = f"""
      <div style="margin-top: 16px;">
        <h4 style="margin: 8px 0;">Meta-Performance Trend ΓÇö Last {len(mpi_trend_values)} Runs (MPI %) {mpi_trend_direction}</h4>
        <canvas id="mpiTrendChart" width="600" height="150"></canvas>
        <p style="font-size: 12px; color: #666; margin-top: 4px;">
          Green = stable (ΓëÑ80%), yellow = mild drift (60-79%), red = degradation (<60%). Rolling mean (dotted gray) shows short-term stability. <strong>Forecast (dashed blue)</strong> projects 5 cycles ahead assuming current trend continues (slope: {mpi_forecast_slope:+.2f}% per cycle).
        </p>
      </div>
"""
        
        meta_section = f"""
    <section id="meta_performance" style="background: {mpi_color}22; padding: 16px; border-radius: 8px; border-left: 4px solid {mpi_color}; margin-bottom: 24px;">
      <h3 style="margin-top: 0;">≡ƒºá Reflex Meta-Performance</h3>
      <div style="display: flex; align-items: center; gap: 16px;">
        <canvas id="metaGauge" width="200" height="120"></canvas>
        <div>
          <p style="font-size: 18px; margin: 4px 0;"><strong>Status:</strong> <span id="metaStatus">{mpi_emoji} {mpi_status}</span></p>
          <p style="margin: 4px 0;"><strong>MPI:</strong> {mpi:.1f}%</p>
          <p style="margin: 4px 0; font-size: 12px; color: #666;">╬öR┬▓: {mpi_delta_r2:+.3f} | Drift: {mpi_drift:+.3f}</p>
        </div>
      </div>
      {consistency_panel}
      {trend_chart}
    </section>
    """
    
    # Build forecast alignment section if available
    alignment_section = ""
    if forecast_alignment:
        alignment_corr = forecast_alignment.get("rei_mpi_correlation", 0.0)
        alignment_class = forecast_alignment.get("classification", "Unknown")
        rei_values_align = forecast_alignment.get("rei_values", [])
        mpi_values_align = forecast_alignment.get("mpi_values", [])
        
        # Color based on classification
        if alignment_class == "Aligned improvement":
            align_color = "#2cbe4e"
            align_emoji = "Γ£à"
        elif alignment_class == "Diverging signals":
            align_color = "#d73a49"
            align_emoji = "ΓÜá∩╕Å"
        else:
            align_color = "#dfb317"
            align_emoji = "Γ₧í∩╕Å"
        
        alignment_section = f"""
    <section id="forecast_alignment" style="background: {align_color}22; padding: 16px; border-radius: 8px; border-left: 4px solid {align_color}; margin-bottom: 24px;">
      <h3 style="margin-top: 0;">≡ƒöù Forecast Alignment (REIΓÇôMPI Correlation)</h3>
      <div style="display: flex; align-items: flex-start; gap: 16px;">
        <canvas id="alignmentScatter" width="400" height="300"></canvas>
        <div>
          <p style="font-size: 18px; margin: 4px 0;"><strong>Correlation:</strong> r = {alignment_corr:+.3f}</p>
          <p style="font-size: 16px; margin: 4px 0;">{align_emoji} {alignment_class}</p>
          <p style="margin: 8px 0 4px 0; font-size: 14px; color: #666;"><strong>Interpretation:</strong></p>
          <p style="margin: 4px 0; font-size: 13px; color: #666;">
            {"Policy effectiveness and meta-learning move together. Forecasts are mutually reinforcing." if alignment_class == "Aligned improvement" else 
             "Policy and meta-learning are anti-correlated. Investigate discrepancies between REI and MPI trends." if alignment_class == "Diverging signals" else
             "Weak correlation. Policy effectiveness and meta-learning are loosely coupled."}
          </p>
          <p style="margin: 8px 0 4px 0; font-size: 12px; color: #999;">
            Scatter shows {len(rei_values_align)} recent samples with best-fit line.
          </p>
        </div>
      </div>
    </section>
    """
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Reflex Feedback Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
    h1 {{ margin-bottom: 8px; }}
    .status {{ background: #f5f5f5; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; }}
    .grid {{ display: grid; grid-template-columns: 1fr; gap: 24px; }}
    canvas {{ width: 100%; max-width: 900px; height: 300px; border: 1px solid #eee; background: #fff; cursor: crosshair; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 900px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; }}
    th {{ background: #fafafa; text-align: left; }}
    .foot {{ margin-top: 16px; color: #666; font-size: 13px; }}
    #mpiTooltip {{ position: absolute; display: none; background: #222; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 12px; pointer-events: none; z-index: 1000; }}
  </style>
</head>
<body>
  <div id="mpiTooltip"></div>
  <h1>Reflex Feedback Dashboard</h1>
  <div class="status">
    <strong>Current Status:</strong> REI {current_rei:+.2f} {current_emoji} {current_class} | RSI {current_rsi:.1f}% | GHS {current_ghs:.1f}%
  </div>
  
  {meta_section}
  
  {standalone_consistency_panel}
  
  {alignment_section}
  
  <div class="grid">
    <div>
      <h3>REI Trend (Reflex Effectiveness Index)</h3>
      <canvas id="reiChart"></canvas>
    </div>
    
    <div>
      <h3>RSI vs GHS Timeline</h3>
      <canvas id="rsiGhsChart"></canvas>
    </div>
    
    <div>
      <h3>Recent Reflex Decisions</h3>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Timestamp</th>
            <th>Policy Mode</th>
            <th>REI</th>
            <th>Classification</th>
          </tr>
        </thead>
        <tbody>
          {decision_rows}
        </tbody>
      </table>
    </div>
  </div>
  
  <div class="foot">Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</div>
  
  <script>
  (function() {{
    const reiLabels = {json.dumps(rei_labels)};
    const reiValues = {json.dumps(rei_values)};
    const reiColors = {json.dumps(rei_colors)};
    
    const rsiLabels = {json.dumps(rsi_labels)};
    const rsiValues = {json.dumps(rsi_values)};
    
    const ghsLabels = {json.dumps(ghs_labels)};
    const ghsValues = {json.dumps(ghs_values)};
    
    function drawREI(id) {{
      const c = document.getElementById(id);
      if (!c) return;
      const ctx = c.getContext('2d');
      const W = c.width = c.clientWidth * devicePixelRatio;
      const H = c.height = c.clientHeight * devicePixelRatio;
      ctx.scale(devicePixelRatio, devicePixelRatio);
      
      const pad = 40;
      const w = c.clientWidth - pad * 2;
      const h = c.clientHeight - pad * 2;
      
      if (reiValues.length === 0) {{
        ctx.fillStyle = '#666';
        ctx.font = '14px Arial';
        ctx.fillText('No REI data available yet', pad, c.clientHeight / 2);
        return;
      }}
      
      const maxY = Math.max(5, ...reiValues.map(Math.abs));
      const minY = -maxY;
      
      function xv(i) {{ return pad + (i / (reiValues.length - 1 || 1)) * w; }}
      function yv(v) {{ return c.clientHeight - pad - ((v - minY) / (maxY - minY)) * h; }}
      
      // Axes
      ctx.strokeStyle = '#999'; ctx.lineWidth = 1;
      ctx.beginPath();
      const zeroY = yv(0);
      ctx.moveTo(pad, pad);
      ctx.lineTo(pad, c.clientHeight - pad);
      ctx.lineTo(c.clientWidth - pad, c.clientHeight - pad);
      ctx.stroke();
      
      // Zero line
      ctx.strokeStyle = '#ccc'; ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad, zeroY);
      ctx.lineTo(c.clientWidth - pad, zeroY);
      ctx.stroke();
      
      // Line segments with color transitions
      for (let i = 1; i < reiValues.length; i++) {{
        ctx.strokeStyle = reiColors[i];
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(xv(i - 1), yv(reiValues[i - 1]));
        ctx.lineTo(xv(i), yv(reiValues[i]));
        ctx.stroke();
      }}
      
      // Points
      for (let i = 0; i < reiValues.length; i++) {{
        ctx.fillStyle = reiColors[i];
        ctx.beginPath();
        ctx.arc(xv(i), yv(reiValues[i]), 5, 0, Math.PI * 2);
        ctx.fill();
      }}
      
      // Labels
      ctx.fillStyle = '#222'; ctx.font = '11px Arial';
      const step = Math.ceil(reiLabels.length / 8) || 1;
      for (let i = 0; i < reiLabels.length; i++) {{
        if (i % step === 0 || i === reiLabels.length - 1) {{
          ctx.save();
          ctx.translate(xv(i), c.clientHeight - 10);
          ctx.rotate(-Math.PI / 4);
          ctx.fillText(reiLabels[i], 0, 0);
          ctx.restore();
        }}
      }}
    }}
    
    function drawRSIGHS(id) {{
      const c = document.getElementById(id);
      if (!c) return;
      const ctx = c.getContext('2d');
      const W = c.width = c.clientWidth * devicePixelRatio;
      const H = c.height = c.clientHeight * devicePixelRatio;
      ctx.scale(devicePixelRatio, devicePixelRatio);
      
      const pad = 40;
      const w = c.clientWidth - pad * 2;
      const h = c.clientHeight - pad * 2;
      
      if (rsiValues.length === 0) {{
        ctx.fillStyle = '#666';
        ctx.font = '14px Arial';
        ctx.fillText('No RSI/GHS data available yet', pad, c.clientHeight / 2);
        return;
      }}
      
      const maxRSI = 100;
      const minRSI = 0;
      const maxGHS = Math.max(100, ...ghsValues);
      const minGHS = 0;
      
      function xv(i, len) {{ return pad + (i / (len - 1 || 1)) * w; }}
      function yvRSI(v) {{ return c.clientHeight - pad - ((v - minRSI) / (maxRSI - minRSI)) * h; }}
      function yvGHS(v) {{ return c.clientHeight - pad - ((v - minGHS) / (maxGHS - minGHS)) * h; }}
      
      // Axes
      ctx.strokeStyle = '#999'; ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad, pad);
      ctx.lineTo(pad, c.clientHeight - pad);
      ctx.lineTo(c.clientWidth - pad, c.clientHeight - pad);
      ctx.stroke();
      
      // RSI line
      ctx.strokeStyle = '#0366d6'; ctx.lineWidth = 2;
      ctx.beginPath();
      for (let i = 0; i < rsiValues.length; i++) {{
        const x = xv(i, rsiValues.length);
        const y = yvRSI(rsiValues[i]);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }}
      ctx.stroke();
      
      // GHS line (if available)
      if (ghsValues.length > 0) {{
        ctx.strokeStyle = '#f39c12'; ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = 0; i < ghsValues.length; i++) {{
          const x = xv(i, ghsValues.length);
          const y = yvGHS(ghsValues[i]);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }}
        ctx.stroke();
      }}
      
      // Legend
      ctx.fillStyle = '#0366d6'; ctx.fillRect(pad, pad - 20, 12, 12);
      ctx.fillStyle = '#222'; ctx.font = '12px Arial';
      ctx.fillText('RSI', pad + 16, pad - 10);
      
      ctx.fillStyle = '#f39c12'; ctx.fillRect(pad + 60, pad - 20, 12, 12);
      ctx.fillText('GHS', c.clientWidth - pad + 25, pad + 12);
    }}
    
    function drawMetaGauge(id, mpi, color) {{
      const c = document.getElementById(id);
      if (!c) return;
      const ctx = c.getContext('2d');
      const w = c.width;
      const h = c.height;
      const cx = w / 2;
      const cy = h - 10;
      const radius = Math.min(w, h * 2) / 2 - 20;
      
      // Background arc (gray)
      ctx.lineWidth = 12;
      ctx.strokeStyle = '#e0e0e0';
      ctx.beginPath();
      ctx.arc(cx, cy, radius, Math.PI, 0, false);
      ctx.stroke();
      
      // MPI arc (colored based on status)
      const mpiAngle = Math.PI + (mpi / 100) * Math.PI;
      ctx.strokeStyle = color;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, Math.PI, mpiAngle, false);
      ctx.stroke();
      
      // Needle
      const needleAngle = Math.PI + (mpi / 100) * Math.PI;
      const needleLen = radius - 10;
      ctx.strokeStyle = '#333';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + needleLen * Math.cos(needleAngle), cy + needleLen * Math.sin(needleAngle));
      ctx.stroke();
      
      // Center dot
      ctx.fillStyle = '#333';
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, 2 * Math.PI);
      ctx.fill();
      
      // Labels
      ctx.fillStyle = '#666';
      ctx.font = '12px Arial';
      ctx.textAlign = 'left';
      ctx.fillText('0%', cx - radius - 5, cy + 5);
      ctx.textAlign = 'right';
      ctx.fillText('100%', cx + radius + 5, cy + 5);
    }}

    function drawConsistencyGauge(id, score, accentColor) {{
      const c = document.getElementById(id);
      if (!c) return;
      const ctx = c.getContext('2d');
      const w = c.width;
      const h = c.height;
      const cx = w / 2;
      const cy = h - 10;
      const radius = Math.min(w, h * 2) / 2 - 20;

      const segments = [
        {{ start: 0.0, end: 0.5, color: '#d73a49' }},
        {{ start: 0.5, end: 0.75, color: '#dfb317' }},
        {{ start: 0.75, end: 1.0, color: '#2cbe4e' }},
      ];

      ctx.lineWidth = 12;
      ctx.lineCap = 'round';
      segments.forEach(seg => {{
        const startAngle = Math.PI + seg.start * Math.PI;
        const endAngle = Math.PI + seg.end * Math.PI;
        ctx.strokeStyle = seg.color;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, startAngle, endAngle, false);
        ctx.stroke();
      }});

      const normalized = Math.max(0, Math.min(score / 100, 1));
      const gaugeAngle = Math.PI + normalized * Math.PI;

      ctx.lineWidth = 6;
      ctx.strokeStyle = accentColor;
      ctx.beginPath();
      ctx.arc(cx, cy, radius - 8, Math.PI, gaugeAngle, false);
      ctx.stroke();

      const needleLen = radius - 10;
      ctx.strokeStyle = '#333';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + needleLen * Math.cos(gaugeAngle), cy + needleLen * Math.sin(gaugeAngle));
      ctx.stroke();

      ctx.fillStyle = '#333';
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, 2 * Math.PI);
      ctx.fill();

      const tickValues = [0, 50, 75, 100];
      ctx.lineWidth = 2;
      ctx.strokeStyle = '#bbb';
      tickValues.forEach(val => {{
        const angle = Math.PI + (val / 100) * Math.PI;
        const outer = radius + 2;
        const inner = radius - 10;
        ctx.beginPath();
        ctx.moveTo(cx + inner * Math.cos(angle), cy + inner * Math.sin(angle));
        ctx.lineTo(cx + outer * Math.cos(angle), cy + outer * Math.sin(angle));
        ctx.stroke();
      }});

      ctx.fillStyle = '#666';
      ctx.font = '10px Arial';
      ctx.textAlign = 'center';
      tickValues.forEach(val => {{
        const angle = Math.PI + (val / 100) * Math.PI;
        const labelRadius = radius + 14;
        const tx = cx + labelRadius * Math.cos(angle);
        const ty = cy + labelRadius * Math.sin(angle);
        ctx.fillText(`${{val}}%`, tx, ty + 4);
      }});
    }}
    
    function drawMPITrend(id, data, labels, forecast) {{
      const c = document.getElementById(id);
      if (!c || data.length === 0) return;
      
      const ctx = c.getContext('2d');
      const W = c.width = c.clientWidth * devicePixelRatio;
      const H = c.height = c.clientHeight * devicePixelRatio;
      ctx.scale(devicePixelRatio, devicePixelRatio);
      
      const pad = 40;
      const w = c.clientWidth - pad * 2;
      const h = c.clientHeight - pad * 2;
      
      // Gridlines (horizontal at 0%, 20%, 40%, 60%, 80%, 100%)
      ctx.strokeStyle = '#f0f0f0';
      ctx.lineWidth = 1;
      for (let pct = 0; pct <= 100; pct += 20) {{
        const y = c.clientHeight - pad - (pct / 100) * h;
        ctx.beginPath();
        ctx.moveTo(pad, y);
        ctx.lineTo(c.clientWidth - pad, y);
        ctx.stroke();
      }}
      
      // Axes
      ctx.strokeStyle = '#ddd';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad, pad);
      ctx.lineTo(pad, c.clientHeight - pad);
      ctx.lineTo(c.clientWidth - pad, c.clientHeight - pad);
      ctx.stroke();
      
      // Calculate trend direction
      let trendDir = 'ΓåÆ';
      if (data.length >= 2) {{
        const firstHalf = data.slice(0, Math.floor(data.length / 2));
        const secondHalf = data.slice(Math.floor(data.length / 2));
        const avgFirst = firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length;
        const avgSecond = secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length;
        const delta = avgSecond - avgFirst;
        if (delta > 5) trendDir = 'Γåæ';
        else if (delta < -5) trendDir = 'Γåô';
      }}
      
      // Draw line
      const latest = data[data.length - 1];
      const lineColor = latest >= 80 ? '#2cbe4e' : latest >= 60 ? '#dfb317' : '#d73a49';
      
      ctx.strokeStyle = lineColor;
      ctx.lineWidth = 2;
      ctx.beginPath();
      
      for (let i = 0; i < data.length; i++) {{
        const x = pad + (i / (data.length - 1 || 1)) * w;
        const y = c.clientHeight - pad - (data[i] / 100) * h;
        
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        
        // Draw point
        ctx.fillStyle = lineColor;
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, 2 * Math.PI);
        ctx.fill();
      }}
      
      ctx.stroke();
      
      // Compute and draw rolling mean (5-point window)
      const rolling = [];
      for (let i = 0; i < data.length; i++) {{
        const start = Math.max(0, i - 4);
        const subset = data.slice(start, i + 1);
        const mean = subset.reduce((a, b) => a + b, 0) / subset.length;
        rolling.push(mean);
      }}
      
      ctx.beginPath();
      ctx.setLineDash([5, 5]);
      ctx.strokeStyle = '#999';
      ctx.lineWidth = 1.5;
      for (let i = 0; i < rolling.length; i++) {{
        const x = pad + (i / (data.length - 1 || 1)) * w;
        const y = c.clientHeight - pad - (rolling[i] / 100) * h;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }}
      ctx.stroke();
      ctx.setLineDash([]);
      
      // Draw forecast projection (dashed blue line extending 5 cycles ahead)
      if (forecast && forecast.length > 0) {{
        ctx.beginPath();
        ctx.setLineDash([8, 4]);
        ctx.strokeStyle = '#2196F3';  // Blue to distinguish from historical
        ctx.lineWidth = 2;
        
        // Start from last historical data point
        const lastX = pad + ((data.length - 1) / (data.length - 1 || 1)) * w;
        const lastY = c.clientHeight - pad - (data[data.length - 1] / 100) * h;
        ctx.moveTo(lastX, lastY);
        
        // Draw forecast points
        const forecastExtension = w * 0.4;  // Extend 40% of chart width
        for (let i = 0; i < forecast.length; i++) {{
          const x = lastX + ((i + 1) / forecast.length) * forecastExtension;
          const y = c.clientHeight - pad - (forecast[i] / 100) * h;
          ctx.lineTo(x, y);
          
          // Draw forecast point
          ctx.fillStyle = '#2196F3';
          ctx.save();
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.arc(x, y, 2, 0, 2 * Math.PI);
          ctx.fill();
          ctx.restore();
        }}
        ctx.stroke();
        ctx.setLineDash([]);
      }}
      
      // Labels
      ctx.fillStyle = '#666';
      ctx.font = '11px Arial';
      ctx.textAlign = 'center';
      for (let i = 0; i < labels.length; i++) {{
        const x = pad + (i / (data.length - 1 || 1)) * w;
        ctx.fillText(labels[i], x, c.clientHeight - pad + 15);
      }}
      
      // Y-axis labels
      ctx.textAlign = 'right';
      ctx.fillText('0%', pad - 5, c.clientHeight - pad);
      ctx.fillText('50%', pad - 5, c.clientHeight - pad - h / 2);
      ctx.fillText('100%', pad - 5, pad + 5);
      
      // Add tooltip interactivity
      const tooltip = document.getElementById('mpiTooltip');
      c.addEventListener('mousemove', (e) => {{
        const rect = c.getBoundingClientRect();
        const mouseX = e.clientX - rect.left - pad;
        const pointSpacing = w / (data.length - 1 || 1);
        const idx = Math.round(mouseX / pointSpacing);
        
        if (idx >= 0 && idx < data.length) {{
          tooltip.style.left = (e.clientX + 10) + 'px';
          tooltip.style.top = (e.clientY - 30) + 'px';
          tooltip.innerHTML = `<strong>Run ${{idx + 1}}</strong><br>MPI: ${{data[idx].toFixed(1)}}%<br>${{labels[idx]}}`;
          tooltip.style.display = 'block';
        }} else {{
          tooltip.style.display = 'none';
        }}
      }});
      
      c.addEventListener('mouseleave', () => {{
        tooltip.style.display = 'none';
      }});
    }}
    
    function drawAlignmentScatter(id, reiData, mpiData, correlation, classification) {{
      const c = document.getElementById(id);
      if (!c || reiData.length === 0 || mpiData.length === 0) return;
      
      const ctx = c.getContext('2d');
      const W = c.width = c.clientWidth * devicePixelRatio;
      const H = c.height = c.clientHeight * devicePixelRatio;
      ctx.scale(devicePixelRatio, devicePixelRatio);
      
      const pad = 50;
      const w = c.clientWidth - pad * 2;
      const h = c.clientHeight - pad * 2;
      
      // Find data ranges
      const reiMin = Math.min(...reiData);
      const reiMax = Math.max(...reiData);
      const mpiMin = Math.min(...mpiData);
      const mpiMax = Math.max(...mpiData);
      
      // Expand ranges slightly for padding
      const reiRange = reiMax - reiMin || 1;
      const mpiRange = mpiMax - mpiMin || 1;
      const reiPad = reiRange * 0.1;
      const mpiPad = mpiRange * 0.1;
      
      const xMin = reiMin - reiPad;
      const xMax = reiMax + reiPad;
      const yMin = mpiMin - mpiPad;
      const yMax = mpiMax + mpiPad;
      
      // Mapping functions
      const xMap = (rei) => pad + ((rei - xMin) / (xMax - xMin)) * w;
      const yMap = (mpi) => c.clientHeight - pad - ((mpi - yMin) / (yMax - yMin)) * h;
      
      // Draw axes
      ctx.strokeStyle = '#999';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad, pad);
      ctx.lineTo(pad, c.clientHeight - pad);
      ctx.lineTo(c.clientWidth - pad, c.clientHeight - pad);
      ctx.stroke();
      
      // Grid lines
      ctx.strokeStyle = '#f0f0f0';
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {{
        // Vertical
        const x = pad + (i / 4) * w;
        ctx.beginPath();
        ctx.moveTo(x, pad);
        ctx.lineTo(x, c.clientHeight - pad);
        ctx.stroke();
        
        // Horizontal
        const y = c.clientHeight - pad - (i / 4) * h;
        ctx.beginPath();
        ctx.moveTo(pad, y);
        ctx.lineTo(c.clientWidth - pad, y);
        ctx.stroke();
      }}
      
      // Best-fit line (linear regression)
      if (reiData.length >= 2) {{
        const n = reiData.length;
        let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
        for (let i = 0; i < n; i++) {{
          sumX += reiData[i];
          sumY += mpiData[i];
          sumXY += reiData[i] * mpiData[i];
          sumX2 += reiData[i] * reiData[i];
        }}
        
        const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
        const intercept = (sumY - slope * sumX) / n;
        
        // Draw line
        ctx.strokeStyle = '#999';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        const x1 = xMin;
        const y1 = slope * x1 + intercept;
        const x2 = xMax;
        const y2 = slope * x2 + intercept;
        ctx.moveTo(xMap(x1), yMap(y1));
        ctx.lineTo(xMap(x2), yMap(y2));
        ctx.stroke();
        ctx.setLineDash([]);
      }}
      
      // Draw points (color by classification)
      let pointColor = '#2cbe4e';  // green
      if (classification === 'Diverging signals') {{
        pointColor = '#d73a49';  // red
      }} else if (classification === 'Neutral coupling') {{
        pointColor = '#dfb317';  // yellow
      }}
      
      ctx.fillStyle = pointColor;
      for (let i = 0; i < reiData.length; i++) {{
        const x = xMap(reiData[i]);
        const y = yMap(mpiData[i]);
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, 2 * Math.PI);
        ctx.fill();
      }}
      
      // Axis labels
      ctx.fillStyle = '#666';
      ctx.font = '12px Arial';
      ctx.textAlign = 'center';
      ctx.fillText('REI', c.clientWidth / 2, c.clientHeight - 10);
      
      ctx.save();
      ctx.translate(15, c.clientHeight / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText('MPI (%)', 0, 0);
      ctx.restore();
      
      // Axis tick labels
      ctx.textAlign = 'center';
      ctx.fillText(xMin.toFixed(2), pad, c.clientHeight - pad + 15);
      ctx.fillText(xMax.toFixed(2), c.clientWidth - pad, c.clientHeight - pad + 15);
      
      ctx.textAlign = 'right';
      ctx.fillText(yMin.toFixed(0), pad - 5, c.clientHeight - pad);
      ctx.fillText(yMax.toFixed(0), pad - 5, pad + 5);
    }}
    
    drawREI('reiChart');
    drawRSIGHS('rsiGhsChart');
    if (document.getElementById('metaGauge')) {{
      drawMetaGauge('metaGauge', {mpi:.1f}, '{mpi_color}');
    }}
    if (document.getElementById('consistencyGauge')) {{
      drawConsistencyGauge('consistencyGauge', {stability_score_for_js:.1f}, '{stability_color_value}');
    }}
    if (document.getElementById('mpiTrendChart')) {{
      const mpiTrendData = {json.dumps(mpi_trend_values)};
      const mpiTrendLabels = {json.dumps(mpi_trend_labels)};
      const mpiForecast = {json.dumps(mpi_forecast_values)};
      drawMPITrend('mpiTrendChart', mpiTrendData, mpiTrendLabels, mpiForecast);
    }}
    if (document.getElementById('alignmentScatter')) {{
      const reiAlign = {json.dumps(rei_values_align if forecast_alignment else [])};
      const mpiAlign = {json.dumps(mpi_values_align if forecast_alignment else [])};
      const alignCorr = {json.dumps(alignment_corr if forecast_alignment else 0.0)};
      const alignClass = {json.dumps(alignment_class if forecast_alignment else "Unknown")};
      drawAlignmentScatter('alignmentScatter', reiAlign, mpiAlign, alignCorr, alignClass);
    }}
  }})();
  </script>
</body>
</html>
"""
    return html, mpi_forecast_slope, stability_snapshot


def update_audit_summary(
    summary_path: str,
    last_rei: float,
    classification: str,
    current_rsi: float,
    current_ghs: float,
    meta_performance: Dict[str, Any] = None,
    forecast_alignment: Dict[str, Any] = None,
    forecast_consistency: Dict[str, Any] = None,
    updated_timestamp: Optional[str] = None,
) -> None:
    """Update audit summary with reflex feedback block (idempotent)."""
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "# Audit Summary\n\n"
    
    emoji = get_classification_emoji(classification)
    
    info_segments: List[str] = []

    if meta_performance:
        mpi_val = meta_performance.get("mpi", 0.0)
        mpi_status = meta_performance.get("classification", "Unknown")
        mpi_slope = meta_performance.get("forecast_slope", 0.0)
        if mpi_val >= 80:
            mpi_emoji = "≡ƒƒó"
        elif mpi_val >= 60:
            mpi_emoji = "≡ƒƒí"
        else:
            mpi_emoji = "≡ƒö┤"
        info_segments.append(
            f"MPI {mpi_val:.1f}% {mpi_emoji} {mpi_status}, trend chart rendered, forecast projection slope {mpi_slope:+.2f}% (5 runs)"
        )

    if forecast_alignment:
        align_corr = forecast_alignment.get("rei_mpi_correlation", 0.0)
        align_class = forecast_alignment.get("classification", "Unknown")
        info_segments.append(
            f"Alignment panel rendered (r={align_corr:+.3f}, {align_class})"
        )

    if isinstance(forecast_consistency, dict):
        stability_score = forecast_consistency.get("stability_score")
        if stability_score is not None:
            stability_label = forecast_consistency.get("stability_label", "Consistency assessed")
            stability_emoji = forecast_consistency.get("stability_emoji", "🟢")
            info_segments.append(
                f"Forecast consistency gauge rendered — {stability_emoji} {stability_label} ({stability_score:.1f}%)"
            )

    info_suffix = ""
    if info_segments:
        info_suffix = " | " + " | ".join(info_segments)

    normalized_ts: Optional[str] = None
    if updated_timestamp:
        try:
            parsed = datetime.fromisoformat(updated_timestamp.replace("Z", "+00:00"))
            normalized_ts = parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            normalized_ts = None
    if not normalized_ts:
        normalized_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    block = (
        f"{AUDIT_MARKER_BEGIN}\n"
    f"Updated: {normalized_ts}\n"
        f"Reflex Feedback: last REI {last_rei:+.2f} {emoji} {classification}, "
        f"RSIΓåÆ{current_rsi:.1f}%, GHSΓåÆ{current_ghs:.1f}%{info_suffix}.\n"
        f"{AUDIT_MARKER_END}"
    )
    
    # Check if markers exist
    if AUDIT_MARKER_BEGIN in content and AUDIT_MARKER_END in content:
        # Replace existing block
        pattern = re.compile(
            re.escape(AUDIT_MARKER_BEGIN) + r"[\s\S]*?" + re.escape(AUDIT_MARKER_END),
            re.MULTILINE
        )
        content = pattern.sub(block, content)
    else:
        # Append at end
        content = content.rstrip() + "\n\n" + block + "\n"
    
    # Atomic write
    tmp = summary_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, summary_path)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Reflex Feedback Dashboard - visualize REI trends and RSI/GHS timeline"
    )
    parser.add_argument(
        "--reflex",
        default="reports/reflex_evaluation.json",
        help="Path to reflex evaluation report"
    )
    parser.add_argument(
        "--history",
        default="logs/regime_stability_history.json",
        help="Path to regime stability history"
    )
    parser.add_argument(
        "--health",
        default="reports/governance_health.json",
        help="Path to governance health report"
    )
    parser.add_argument(
        "--actions-log",
        default="logs/regime_policy_actions.json",
        help="Path to policy actions log (for REI history)"
    )
    parser.add_argument(
        "--output",
        default="reports/reflex_feedback_dashboard.html",
        help="Path to output dashboard HTML"
    )
    parser.add_argument(
        "--audit-summary",
        default="reports/audit_summary.md",
        help="Path to audit summary markdown"
    )
    parser.add_argument(
        "--meta-performance",
        default="reports/reflex_meta_performance.json",
        help="Path to reflex meta-performance report"
    )
    parser.add_argument(
        "--model-history",
        default="logs/reflex_model_history.json",
        help="Path to reflex learning model history"
    )
    parser.add_argument(
        "--forecast-alignment",
        default="reports/reflex_forecast_alignment.json",
        help="Path to forecast alignment report"
    )
    parser.add_argument(
        "--forecast-consistency",
        default="reports/forecast_consistency.json",
        help="Path to forecast consistency monitor output"
    )
    
    args = parser.parse_args(argv)
    
    # Load current evaluation
    current_eval = load_json(args.reflex, {})
    
    # Load meta-performance
    meta_perf = load_json(args.meta_performance, {})
    
    # Load model history
    model_hist = load_json(args.model_history, [])
    if not isinstance(model_hist, list):
        model_hist = []
    
    # Load forecast alignment
    forecast_align = load_json(args.forecast_alignment, {})

    # Load forecast consistency monitor output
    forecast_consistency = load_json(args.forecast_consistency, {})
    if not isinstance(forecast_consistency, dict):
        forecast_consistency = {}
    
    # Load RSI history
    rsi_hist_data = load_json(args.history, {})
    rsi_series = []
    if isinstance(rsi_hist_data, dict) and isinstance(rsi_hist_data.get("rsi"), list):
        rsi_series = rsi_hist_data["rsi"]
    
    # Load health history (or current only)
    health_data = load_json(args.health, {})
    current_ghs = float(health_data.get("GovernanceHealthScore", 0.0))
    
    # Build GHS history (placeholder - in real scenario would need history)
    ghs_series = []
    if rsi_series:
        # Simulate GHS history aligned with RSI timestamps
        for entry in rsi_series:
            ghs_series.append({
                "timestamp": entry.get("timestamp", ""),
                "ghs": current_ghs  # In practice, read from governance_history
            })
    
    # Load policy actions for REI history
    actions = load_json(args.actions_log, [])
    
    # Build REI history from actions + evaluations
    # For simplicity, we'll use the current evaluation as the last entry
    # In a real scenario, we'd maintain a separate reflex_history.json
    rei_history = []
    if actions:
        for action in actions:
            # Placeholder: assume each action has an evaluation
            rei_history.append({
                "timestamp": action.get("timestamp", ""),
                "policy_mode": action.get("mode", "N/A"),
                "rei": 0.0,  # Would be populated from actual evaluations
                "classification": "Neutral"
            })
    
    # Add current evaluation
    if current_eval and current_eval.get("status") == "ok":
        rei_history.append({
            "timestamp": current_eval.get("timestamp", ""),
            "policy_mode": current_eval.get("policy_mode", "N/A"),
            "rei": current_eval.get("rei", 0.0),
            "classification": current_eval.get("classification", "Neutral")
        })
    
    # Build dashboard
    html, forecast_slope, stability_snapshot = build_dashboard_html(
        rei_history,
        rsi_series,
        ghs_series,
        current_eval,
        meta_perf,
        model_hist,
        forecast_align,
        forecast_consistency,
    )
    
    # Add forecast slope to meta_perf for audit summary
    if meta_perf is None:
        meta_perf = {}
    meta_perf["forecast_slope"] = forecast_slope
    
    # Write dashboard
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    
    # Update audit summary
    last_rei = current_eval.get("rei", 0.0)
    classification = current_eval.get("classification", "Neutral")
    current_rsi = current_eval.get("current_rsi", 100.0)
    
    update_audit_summary(
        summary_path=args.audit_summary,
        last_rei=last_rei,
        classification=classification,
        current_rsi=current_rsi,
        current_ghs=current_ghs,
        meta_performance=meta_perf,
        forecast_alignment=forecast_align,
        forecast_consistency=forecast_consistency,
        updated_timestamp=current_eval.get("timestamp"),
    )
    
    # Output summary
    result = {
        "status": "ok",
        "dashboard": args.output,
        "rei_entries": len(rei_history),
        "last_rei": last_rei,
        "classification": classification,
    }
    if stability_snapshot:
        result["forecast_consistency"] = stability_snapshot
    
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
