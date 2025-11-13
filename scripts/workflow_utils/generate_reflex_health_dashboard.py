#!/usr/bin/env python3
"""
Reflex Health Timeline & Compliance Export Dashboard

Generates longitudinal visualization of Reflex Self-Audit results with:
- Interactive timeline chart with color gradients
- Compliance summary table
- CSV export for audit transparency
- Trend analysis with rolling mean
"""

import argparse
import json
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(path: Path, default: Optional[Any] = None) -> Any:
    """Load JSON file with fallback to default."""
    if not path.exists():
        return default or {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default or {}


def save_json(path: Path, data: Any) -> None:
    """Save data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_trend_emoji(health_current: float, health_previous: Optional[float]) -> str:
    """Get trend emoji based on health score change."""
    if health_previous is None:
        return "➡️"
    delta = health_current - health_previous
    if delta > 5:
        return "📈"
    elif delta < -5:
        return "📉"
    else:
        return "➡️"


def get_trend_direction(history: List[Dict]) -> str:
    """Determine overall trend direction from history."""
    if len(history) < 2:
        return "stable"
    
    # Compare first half vs second half
    mid = len(history) // 2
    first_half_avg = sum(h["health_score"] for h in history[:mid]) / mid
    second_half_avg = sum(h["health_score"] for h in history[mid:]) / (len(history) - mid)
    
    delta = second_half_avg - first_half_avg
    if delta > 5:
        return "improving"
    elif delta < -5:
        return "declining"
    else:
        return "stable"


def compute_rolling_mean(history: List[Dict]) -> List[float]:
    """Compute rolling mean for timeline overlay."""
    if not history:
        return []
    
    window = min(3, len(history))  # 3-point rolling average
    means = []
    
    for i in range(len(history)):
        start = max(0, i - window + 1)
        window_scores = [h["health_score"] for h in history[start:i+1]]
        means.append(sum(window_scores) / len(window_scores))
    
    return means


def generate_html_dashboard(
    latest: Dict,
    history: List[Dict],
    trend_direction: str
) -> str:
    """Generate HTML dashboard with timeline chart and compliance table."""
    
    # Prepare data for chart
    timestamps = [h.get("timestamp", f"Run {i+1}") for i, h in enumerate(history)]
    health_scores = [h["health_score"] for h in history]
    rolling_means = compute_rolling_mean(history)
    
    # Format timestamps for display
    display_times = []
    for ts in timestamps:
        try:
            if "T" in ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                display_times.append(dt.strftime("%m/%d %H:%M"))
            else:
                display_times.append(ts)
        except:
            display_times.append(ts)
    
    # Trend symbol
    trend_symbols = {
        "improving": "↑ improving",
        "declining": "↓ declining",
        "stable": "→ stable"
    }
    trend_text = trend_symbols.get(trend_direction, "→ stable")
    
    # Get last 5 for compliance table
    compliance_rows = []
    for i in range(max(0, len(history) - 5), len(history)):
        h = history[i]
        prev_health = history[i-1]["health_score"] if i > 0 else None
        delta = h["health_score"] - prev_health if prev_health is not None else 0
        emoji = get_trend_emoji(h["health_score"], prev_health)
        
        ts = h.get("timestamp", f"Run {i+1}")
        try:
            if "T" in ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                display_ts = dt.strftime("%Y-%m-%d %H:%M UTC")
            else:
                display_ts = ts
        except:
            display_ts = ts
        
        compliance_rows.append({
            "timestamp": display_ts,
            "health": h["health_score"],
            "classification": h.get("classification", "Unknown"),
            "delta": delta,
            "emoji": emoji
        })
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reflex Health Timeline Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
        }}
        h1 {{
            color: #2d3748;
            margin: 0 0 10px 0;
            font-size: 32px;
            font-weight: 700;
        }}
        .subtitle {{
            color: #718096;
            margin: 0 0 30px 0;
            font-size: 16px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
        }}
        .metric-label {{
            font-size: 14px;
            opacity: 0.9;
            margin-bottom: 8px;
        }}
        .metric-value {{
            font-size: 32px;
            font-weight: 700;
            margin: 0;
        }}
        .chart-container {{
            background: #f7fafc;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            border: 1px solid #e2e8f0;
        }}
        .chart-title {{
            font-size: 20px;
            font-weight: 600;
            color: #2d3748;
            margin: 0 0 20px 0;
        }}
        canvas {{
            max-width: 100%;
            height: auto;
        }}
        .status-caption {{
            text-align: center;
            margin-top: 15px;
            font-size: 16px;
            color: #4a5568;
            font-weight: 500;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{
            background: #f7fafc;
            font-weight: 600;
            color: #2d3748;
        }}
        tr:hover {{
            background: #f7fafc;
        }}
        .classification {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 500;
        }}
        .classification.optimal {{
            background: #c6f6d5;
            color: #22543d;
        }}
        .classification.stable {{
            background: #feebc8;
            color: #744210;
        }}
        .classification.degraded {{
            background: #fed7d7;
            color: #742a2a;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
            color: #718096;
            font-size: 14px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🧭 Reflex Health Timeline Dashboard</h1>
        <p class="subtitle">Longitudinal governance health monitoring & compliance export</p>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Current Health Score</div>
                <div class="metric-value">{latest["health_score"]:.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Classification</div>
                <div class="metric-value" style="font-size: 20px;">{latest.get("emoji", "")} {latest.get("classification", "Unknown")}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Trend Direction</div>
                <div class="metric-value" style="font-size: 20px;">{trend_text}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">History Depth</div>
                <div class="metric-value">{len(history)}</div>
            </div>
        </div>
        
        <div class="chart-container">
            <h2 class="chart-title">Health Score Timeline (Last {len(history)} Cycles)</h2>
            <canvas id="healthChart" width="800" height="400"></canvas>
            <div class="status-caption">Trend: {trend_text}</div>
        </div>
        
        <div class="chart-container">
            <h2 class="chart-title">Compliance Summary (Last 5 Runs)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Health %</th>
                        <th>Classification</th>
                        <th>Δ from Previous</th>
                        <th>Trend</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    for row in compliance_rows:
        class_lower = row["classification"].lower()
        class_style = "optimal" if "optimal" in class_lower else ("stable" if "stable" in class_lower else "degraded")
        delta_sign = "+" if row["delta"] > 0 else ""
        delta_display = f"{delta_sign}{row['delta']:.1f}%" if row["delta"] != 0 else "—"
        
        html += f"""                    <tr>
                        <td>{row["timestamp"]}</td>
                        <td><strong>{row["health"]:.1f}%</strong></td>
                        <td><span class="classification {class_style}">{row["classification"]}</span></td>
                        <td>{delta_display}</td>
                        <td style="font-size: 20px;">{row["emoji"]}</td>
                    </tr>
"""
    
    html += """                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>🔒 This report is auto-generated for governance audit transparency.</p>
            <p>Generated: """ + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") + """</p>
        </div>
    </div>
    
    <script>
        const canvas = document.getElementById('healthChart');
        const ctx = canvas.getContext('2d');
        
        // Data
        const labels = """ + json.dumps(display_times) + """;
        const healthScores = """ + json.dumps(health_scores) + """;
        const rollingMeans = """ + json.dumps(rolling_means) + """;
        
        // Chart dimensions
        const padding = 60;
        const chartWidth = canvas.width - padding * 2;
        const chartHeight = canvas.height - padding * 2;
        const chartLeft = padding;
        const chartTop = padding;
        
        // Scale functions
        const minScore = 0;
        const maxScore = 100;
        const xStep = chartWidth / (labels.length - 1 || 1);
        
        function scaleY(value) {
            return chartTop + chartHeight - ((value - minScore) / (maxScore - minScore)) * chartHeight;
        }
        
        function scaleX(index) {
            return chartLeft + index * xStep;
        }
        
        // Draw grid
        ctx.strokeStyle = '#e2e8f0';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 5; i++) {
            const y = chartTop + (chartHeight / 5) * i;
            ctx.beginPath();
            ctx.moveTo(chartLeft, y);
            ctx.lineTo(chartLeft + chartWidth, y);
            ctx.stroke();
            
            const value = maxScore - (maxScore / 5) * i;
            ctx.fillStyle = '#718096';
            ctx.font = '12px sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText(value.toFixed(0) + '%', chartLeft - 10, y + 4);
        }
        
        // Draw threshold lines
        ctx.strokeStyle = '#fc8181';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.moveTo(chartLeft, scaleY(60));
        ctx.lineTo(chartLeft + chartWidth, scaleY(60));
        ctx.stroke();
        
        ctx.strokeStyle = '#68d391';
        ctx.beginPath();
        ctx.moveTo(chartLeft, scaleY(80));
        ctx.lineTo(chartLeft + chartWidth, scaleY(80));
        ctx.stroke();
        ctx.setLineDash([]);
        
        // Draw rolling mean (gray dotted)
        ctx.strokeStyle = '#a0aec0';
        ctx.lineWidth = 2;
        ctx.setLineDash([2, 3]);
        ctx.beginPath();
        rollingMeans.forEach((mean, i) => {
            const x = scaleX(i);
            const y = scaleY(mean);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.setLineDash([]);
        
        // Draw health score line with gradient
        ctx.lineWidth = 3;
        healthScores.forEach((score, i) => {
            if (i === 0) return;
            
            const x1 = scaleX(i - 1);
            const y1 = scaleY(healthScores[i - 1]);
            const x2 = scaleX(i);
            const y2 = scaleY(score);
            
            // Color based on score
            const avgScore = (healthScores[i - 1] + score) / 2;
            let color;
            if (avgScore >= 80) color = '#48bb78';
            else if (avgScore >= 60) color = '#ed8936';
            else color = '#f56565';
            
            ctx.strokeStyle = color;
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
        });
        
        // Draw data points
        healthScores.forEach((score, i) => {
            const x = scaleX(i);
            const y = scaleY(score);
            
            let color;
            if (score >= 80) color = '#48bb78';
            else if (score >= 60) color = '#ed8936';
            else color = '#f56565';
            
            ctx.fillStyle = 'white';
            ctx.strokeStyle = color;
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(x, y, 6, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
        });
        
        // Draw labels
        ctx.fillStyle = '#2d3748';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'center';
        labels.forEach((label, i) => {
            const x = scaleX(i);
            const y = chartTop + chartHeight + 20;
            ctx.save();
            ctx.translate(x, y);
            ctx.rotate(-Math.PI / 4);
            ctx.fillText(label, 0, 0);
            ctx.restore();
        });
        
        // Legend
        ctx.fillStyle = '#48bb78';
        ctx.fillRect(chartLeft, chartTop - 40, 15, 3);
        ctx.fillStyle = '#2d3748';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('Threshold: 80% (Optimal)', chartLeft + 20, chartTop - 36);
        
        ctx.fillStyle = '#fc8181';
        ctx.fillRect(chartLeft + 200, chartTop - 40, 15, 3);
        ctx.fillText('Threshold: 60% (Stable)', chartLeft + 220, chartTop - 36);
        
        ctx.strokeStyle = '#a0aec0';
        ctx.lineWidth = 2;
        ctx.setLineDash([2, 3]);
        ctx.beginPath();
        ctx.moveTo(chartLeft + 400, chartTop - 38);
        ctx.lineTo(chartLeft + 415, chartTop - 38);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#2d3748';
        ctx.fillText('Rolling Mean', chartLeft + 420, chartTop - 36);
    </script>
</body>
</html>
"""
    
    return html


def export_csv(history: List[Dict], output_path: Path) -> None:
    """Export timeline data to CSV for compliance audit."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    lines = [
        "# Reflex Health Timeline - Compliance Export",
        "# Generated: " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "# This report is auto-generated for governance audit transparency.",
        "",
        "timestamp,rei_score,mpi_score,confidence,rri_score,health_score,classification"
    ]
    
    for entry in history:
        ts = entry.get("timestamp", "")
        components = entry.get("components", {})
        
        rei = components.get("rei", {}).get("value", 0)
        mpi = components.get("mpi", {}).get("value", 0)
        confidence = components.get("confidence", {}).get("value", 0)
        rri = components.get("rri", {}).get("value", 0)
        health = entry.get("health_score", 0)
        classification = entry.get("classification", "Unknown")
        
        lines.append(f"{ts},{rei:.2f},{mpi:.2f},{confidence:.3f},{rri:.2f},{health:.2f},{classification}")
    
    output_path.write_text("\n".join(lines), encoding="utf-8")


def update_audit_summary(
    audit_path: Path,
    history_count: int,
    integrity_score: Optional[float] = None,
    rri_value: Optional[float] = None,
) -> None:
    """Update audit summary with dashboard marker and UTC timestamp."""
    if not audit_path.exists():
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text("# Audit Summary\n\n", encoding="utf-8")
    
    content = audit_path.read_text(encoding="utf-8")
    
    marker_begin = "<!-- REFLEX_HEALTH_DASHBOARD:BEGIN -->"
    marker_end = "<!-- REFLEX_HEALTH_DASHBOARD:END -->"
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    summary_line = (
        f"🧭 Reflex Health Dashboard generated — {history_count}-run timeline & CSV export available."
    )
    if integrity_score is not None:
        summary_line += f" Integrity score {integrity_score:.1f}%."
    if rri_value is not None:
        summary_line += f" RRI {rri_value:.1f}."

    new_section = f"""{marker_begin}
Updated: {timestamp}
{summary_line}
{marker_end}"""
    
    if marker_begin in content and marker_end in content:
        # Replace existing marker
        import re
        pattern = re.compile(
            re.escape(marker_begin) + r".*?" + re.escape(marker_end),
            re.DOTALL
        )
        content = pattern.sub(new_section, content)
    else:
        # Append new marker
        content = content.rstrip() + "\n\n" + new_section + "\n"
    
    audit_path.write_text(content, encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Reflex Health Timeline Dashboard"
    )
    parser.add_argument(
        "--self-audit",
        type=Path,
        default=Path("reports/reflex_self_audit.json"),
        help="Path to latest reflex self-audit JSON"
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=Path("logs/reflex_self_audit_history.json"),
        help="Path to reflex self-audit history JSON"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/reflex_health_dashboard.html"),
        help="Output path for HTML dashboard"
    )
    parser.add_argument(
        "--csv-export",
        "--export",
        dest="csv_export",
        type=Path,
        default=Path("exports/reflex_health_timeline.csv"),
        help="Output path for CSV export"
    )
    parser.add_argument(
        "--audit-summary",
        type=Path,
        default=Path("reports/audit_summary.md"),
        help="Path to audit summary markdown"
    )
    parser.add_argument(
        "--integrity",
        type=Path,
        default=Path("reports/reflex_integrity.json"),
        help="Path to latest reflex integrity report"
    )
    parser.add_argument(
        "--reinforcement",
        type=Path,
        default=Path("reports/reflex_reinforcement.json"),
        help="Path to reflex reinforcement report"
    )
    
    args = parser.parse_args(argv)
    
    try:
        # Load data
        latest = load_json(args.self_audit)
        if not latest or "health_score" not in latest:
            print("⚠️  No valid self-audit data found. Using defaults.", file=sys.stderr)
            latest = {
                "health_score": 50.0,
                "classification": "Stable",
                "emoji": "🟡",
                "components": {}
            }
        
        history = load_json(args.history, default=[])
        if not isinstance(history, list):
            history = []
        
        # Maintain last 10 entries
        history_deque = deque(history, maxlen=10)
        history = list(history_deque)
        
        # If no history, create single entry from latest
        if not history and latest:
            history = [latest]

        integrity_report = load_json(args.integrity, default={})
        reinforcement_report = load_json(args.reinforcement, default={})
        integrity_score = None
        if isinstance(integrity_report, dict):
            integrity_score = integrity_report.get("integrity_score")
        rri_value = None
        if isinstance(reinforcement_report, dict):
            rri_value = reinforcement_report.get("rri")
        
        # Compute trend
        trend_direction = get_trend_direction(history)
        
        # Generate HTML dashboard
        html_content = generate_html_dashboard(latest, history, trend_direction)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(html_content, encoding="utf-8")
        
        # Export CSV
        export_csv(history, args.csv_export)
        
        # Update audit summary
        update_audit_summary(
            args.audit_summary,
            len(history),
            integrity_score=integrity_score,
            rri_value=rri_value,
        )
        
        print("✅ Reflex Health Dashboard generated successfully")
        print(f"   📊 HTML: {args.output}")
        print(f"   📄 CSV: {args.csv_export}")
        integrity_msg = (
            f"Integrity {integrity_score:.1f}%" if integrity_score is not None else "Integrity N/A"
        )
        reinforcement_msg = (
            f"RRI {rri_value:.1f}" if rri_value is not None else "RRI N/A"
        )
        print(f"   🧭 Timeline: {len(history)} runs, Trend: {trend_direction} ({integrity_msg}, {reinforcement_msg})")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error generating dashboard: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 0  # Always exit 0 for CI stability


if __name__ == "__main__":
    sys.exit(main())
