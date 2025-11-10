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
from typing import Any, Dict, List


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
        return "✅"
    elif classification == "Counterproductive":
        return "⚠️"
    else:
        return "➡️"


def build_dashboard_html(
    rei_history: List[Dict[str, Any]],
    rsi_history: List[Dict[str, Any]],
    ghs_history: List[Dict[str, Any]],
    current_evaluation: Dict[str, Any]
) -> str:
    """Build the complete HTML dashboard."""
    
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
    canvas {{ width: 100%; max-width: 900px; height: 300px; border: 1px solid #eee; background: #fff; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 900px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; }}
    th {{ background: #fafafa; text-align: left; }}
    .foot {{ margin-top: 16px; color: #666; font-size: 13px; }}
  </style>
</head>
<body>
  <h1>Reflex Feedback Dashboard</h1>
  <div class="status">
    <strong>Current Status:</strong> REI {current_rei:+.2f} {current_emoji} {current_class} | RSI {current_rsi:.1f}% | GHS {current_ghs:.1f}%
  </div>
  
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
      ctx.fillText('GHS', pad + 76, pad - 10);
    }}
    
    drawREI('reiChart');
    drawRSIGHS('rsiGhsChart');
  }})();
  </script>
</body>
</html>
"""
    return html


def update_audit_summary(
    summary_path: str,
    last_rei: float,
    classification: str,
    current_rsi: float,
    current_ghs: float
) -> None:
    """Update audit summary with reflex feedback block (idempotent)."""
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "# Audit Summary\n\n"
    
    emoji = get_classification_emoji(classification)
    block = (
        f"{AUDIT_MARKER_BEGIN}\n"
        f"Reflex Feedback: last REI {last_rei:+.2f} {emoji} {classification}, "
        f"RSI→{current_rsi:.1f}%, GHS→{current_ghs:.1f}%.\n"
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
    
    args = parser.parse_args(argv)
    
    # Load current evaluation
    current_eval = load_json(args.reflex, {})
    
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
    html = build_dashboard_html(rei_history, rsi_series, ghs_series, current_eval)
    
    # Write dashboard
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    
    # Update audit summary
    last_rei = current_eval.get("rei", 0.0)
    classification = current_eval.get("classification", "Neutral")
    current_rsi = current_eval.get("current_rsi", 100.0)
    
    update_audit_summary(
        args.audit_summary,
        last_rei,
        classification,
        current_rsi,
        current_ghs
    )
    
    # Output summary
    result = {
        "status": "ok",
        "dashboard": args.output,
        "rei_entries": len(rei_history),
        "last_rei": last_rei,
        "classification": classification,
    }
    
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
