"""
Governance Meta-Reflection Generator
Synthesizes human-readable summaries of the system's long-term governance intelligence.
"""
import os
import json
from datetime import datetime

def load_json(path):
    """Load JSON file, return None if not found."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def format_trend(trend):
    """Format trend with emoji."""
    trend_map = {
        'improving': '📈 improving',
        'declining': '📉 declining',
        'stable': '➡️ stable',
        'insufficient_data': '❓ insufficient data'
    }
    return trend_map.get(trend, trend)

def format_mode(mode):
    """Format stabilization mode with emoji."""
    mode_map = {
        'monitor': '👁️ monitoring',
        'adaptive': '🔄 adaptive',
        'active': '⚡ active intervention'
    }
    return mode_map.get(mode, mode)

def format_status(status):
    """Format coherence status with emoji."""
    status_map = {
        'Stable': '✅ stable',
        'Mild Conflict': '⚠️ mild conflict',
        'Severe Conflict': '❌ severe conflict'
    }
    return status_map.get(status, status)

def main():
    # Load all governance reports
    memory = load_json('reports/governance_memory.json') or {}
    equilibrium = load_json('reports/governance_equilibrium.json') or {}
    coherence = load_json('reports/governance_coherence.json') or {}
    health = load_json('reports/governance_health.json') or {}
    stability = load_json('reports/meta_stability.json') or {}
    
    # Extract key metrics
    dominant_mode = memory.get('dominant_mode', 'monitor')
    mode_dist = memory.get('mode_distribution', {'monitor': 100.0})
    cycles_analyzed = memory.get('cycles_analyzed', 0)
    
    trends = memory.get('trends', {})
    ghs_trend = trends.get('ghs', 'insufficient_data')
    msi_trend = trends.get('msi', 'insufficient_data')
    overall_trend = trends.get('overall', 'stable')
    
    metrics = memory.get('metrics', {})
    avg_health = metrics.get('avg_health', 0.0)
    avg_stability = metrics.get('avg_stability', 0.0)
    avg_coherence = metrics.get('avg_coherence', 100.0)
    
    conflicts = memory.get('recurrent_conflicts', [])
    recommendations = memory.get('recommendations', [])
    
    eq_trend = equilibrium.get('trend', 'neutral')
    eq_confidence = equilibrium.get('confidence', 0.0)
    eq_cycles = equilibrium.get('predicted_equilibrium_cycles', 999)
    
    coherence_index = coherence.get('coherence_index', 100.0)
    coherence_status = coherence.get('status', 'Stable')
    
    current_ghs = health.get('ghs', 0.0) or health.get('GovernanceHealthScore', 0.0)
    current_msi = stability.get('meta_stability_index', 0.0)
    
    # Build narrative reflection
    timestamp = datetime.utcnow().isoformat()
    
    # Opening statement
    if cycles_analyzed < 5:
        opening = f"**Governance Intelligence: Early-Stage Observation**\n\nThe system has completed {cycles_analyzed} governance cycle(s), providing initial baseline metrics for self-assessment."
    elif overall_trend == 'improving':
        opening = f"**Governance Intelligence: Positive Evolution**\n\nAnalysis of {cycles_analyzed} governance cycles reveals a system in positive trajectory, demonstrating adaptive capacity and learning effectiveness."
    elif overall_trend == 'declining':
        opening = f"**Governance Intelligence: Attention Required**\n\nAnalysis of {cycles_analyzed} governance cycles indicates declining performance metrics requiring investigation and corrective intervention."
    else:
        opening = f"**Governance Intelligence: Stable Equilibrium**\n\nThe system has maintained stable governance patterns across {cycles_analyzed} cycles, operating within expected parameters."
    
    # Dominant mode narrative
    stable_pct = mode_dist.get('monitor', 0.0) + mode_dist.get('adaptive', 0.0)
    if stable_pct >= 90:
        mode_narrative = f"The system has operated predominantly in {format_mode(dominant_mode)} mode ({stable_pct:.0f}% of cycles), indicating minimal intervention requirements and strong baseline stability."
    elif stable_pct >= 70:
        mode_narrative = f"Operating primarily in {format_mode(dominant_mode)} mode ({stable_pct:.0f}% of cycles), the system demonstrates reasonable stability with occasional adaptive adjustments."
    else:
        mode_narrative = f"The system has required frequent intervention, spending only {stable_pct:.0f}% of cycles in stable modes. Dominant mode: {format_mode(dominant_mode)}. This suggests underlying parameter misalignment or external instability factors."
    
    # Trend analysis
    trend_narrative = f"**Performance Trends:**\n"
    trend_narrative += f"- Governance Health Score (GHS): {format_trend(ghs_trend)} (current: {current_ghs:.1f}%, avg: {avg_health:.1f}%)\n"
    trend_narrative += f"- Meta-Stability Index (MSI): {format_trend(msi_trend)} (current: {current_msi:.1f}%, avg: {avg_stability:.1f}%)\n"
    trend_narrative += f"- Parameter Coherence: {format_status(coherence_status)} at {coherence_index:.1f}% (avg: {avg_coherence:.1f}%)\n"
    
    # Equilibrium assessment
    if eq_trend == 'converging':
        eq_narrative = f"The system is currently **converging toward equilibrium** (confidence: {eq_confidence:.0%}), with stabilization expected within {eq_cycles} cycles. This indicates effective adaptive mechanisms."
    elif eq_trend == 'diverging':
        eq_narrative = f"The system shows **diverging behavior** (confidence: {eq_confidence:.0%}), suggesting destabilization risk. Proactive intervention measures are active to restore balance."
    else:
        eq_narrative = f"The system maintains **neutral equilibrium** (confidence: {eq_confidence:.0%}), neither strongly converging nor diverging. Continued monitoring is appropriate."
    
    # Conflict and anomaly analysis
    if conflicts:
        conflict_narrative = f"**Recurring Patterns Detected:**\n"
        for i, conflict in enumerate(conflicts[:3], 1):
            conflict_narrative += f"{i}. {conflict}\n"
        if len(conflicts) > 3:
            conflict_narrative += f"...and {len(conflicts) - 3} additional pattern(s).\n"
    else:
        conflict_narrative = "**No recurring anomalies detected.** The system exhibits consistent, stable behavior across all monitored dimensions."
    
    # Actionable insights
    if recommendations:
        insight_narrative = f"**Actionable Insights:**\n"
        for i, rec in enumerate(recommendations[:3], 1):
            insight_narrative += f"{i}. {rec}\n"
        if len(recommendations) > 3:
            insight_narrative += f"...and {len(recommendations) - 3} additional recommendation(s).\n"
    else:
        insight_narrative = "**Actionable Insights:**\nSystem operating within normal parameters — continue routine monitoring and adaptive learning cycles."
    
    # Self-assessment summary
    if current_ghs >= 80 and current_msi >= 70 and coherence_index >= 85:
        assessment = "**Self-Assessment: ✅ Healthy**\n\nThe governance system demonstrates strong performance across all dimensions. Adaptive mechanisms are functioning effectively, and the system exhibits robust self-regulation capacity."
    elif current_ghs >= 60 and current_msi >= 50 and coherence_index >= 70:
        assessment = "**Self-Assessment: ⚠️ Moderate**\n\nThe governance system shows acceptable but suboptimal performance. Some areas require attention to prevent degradation. Enhanced monitoring and targeted adjustments recommended."
    else:
        assessment = "**Self-Assessment: ⚠️ Attention Required**\n\nThe governance system exhibits concerning metrics that warrant immediate investigation. Multiple subsystems may require recalibration or structural review."
    
    # Build full reflection document
    reflection = f"""# Governance Meta-Reflection Report

*Generated: {timestamp}*

---

{opening}

## Executive Summary

{mode_narrative}

{trend_narrative}

{eq_narrative}

---

## Detailed Analysis

{conflict_narrative}

{insight_narrative}

---

## Self-Assessment

{assessment}

---

## Metadata

- Analysis Period: {memory.get('summary_period', 'N/A')}
- Cycles Analyzed: {cycles_analyzed}
- Data Quality:
  - GHS Samples: {memory.get('data_quality', {}).get('ghs_samples', 0)}
  - MSI Samples: {memory.get('data_quality', {}).get('msi_samples', 0)}
  - Coherence Samples: {memory.get('data_quality', {}).get('coherence_samples', 0)}
  - Decision Records: {memory.get('data_quality', {}).get('decision_records', 0)}

---

*This reflection was automatically generated by the Governance Meta-Reflection system, synthesizing insights from governance memory, equilibrium forecasting, coherence analysis, health monitoring, and stability assessment subsystems.*
"""
    
    # Write reflection document
    os.makedirs('reports', exist_ok=True)
    with open('reports/governance_meta_reflection.md', 'w', encoding='utf-8') as f:
        f.write(reflection)
    
    # Build compact summary for audit_summary.md
    if coherence_index < 80:
        coherence_emoji = "⚠️"
    else:
        coherence_emoji = "✅"
    
    if conflicts:
        conflict_summary = f"{len(conflicts)} pattern(s) noted"
    else:
        conflict_summary = "no anomalies"
    
    compact_summary = f"system operating in {dominant_mode} mode; {overall_trend} trend; coherence {coherence_emoji} {coherence_index:.0f}%; {conflict_summary}"
    
    # Update audit_summary.md
    summary_path = 'reports/audit_summary.md'
    if os.path.exists(summary_path):
        with open(summary_path, 'r', encoding='utf-8') as f:
            md = f.read()
    else:
        md = "# Audit Summary\n\n"
    
    start = md.find('<!-- GOVERNANCE_REFLECTION:BEGIN -->')
    end = md.find('<!-- GOVERNANCE_REFLECTION:END -->')
    
    block = f"""
<!-- GOVERNANCE_REFLECTION:BEGIN -->
**Governance Meta-Reflection**

🪞 Meta-reflection: {compact_summary}

- Updated: {timestamp}
- Full report: [governance_meta_reflection.md](governance_meta_reflection.md)
<!-- GOVERNANCE_REFLECTION:END -->
"""
    
    if start != -1 and end != -1:
        md = md[:start] + block + md[end+len('<!-- GOVERNANCE_REFLECTION:END -->'):]
    else:
        md += '\n' + block
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(md)
    
    # Print output for CI
    output = {
        'timestamp': timestamp,
        'cycles_analyzed': cycles_analyzed,
        'dominant_mode': dominant_mode,
        'overall_trend': overall_trend,
        'coherence_index': coherence_index,
        'conflicts_detected': len(conflicts),
        'summary': compact_summary
    }
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
