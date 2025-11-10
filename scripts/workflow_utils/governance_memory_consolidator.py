"""
Governance Memory Consolidator
Summarizes long-term governance history and extracts recurring stability or conflict patterns.
"""
import os
import json
import statistics
from datetime import datetime
from collections import Counter

def load_json(path):
    """Load JSON file, return None if not found."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def save_json(path, data):
    """Save data to JSON file."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def compute_trend(values):
    """Compute simple trend direction from values."""
    if len(values) < 2:
        return "insufficient_data"
    first_half = values[:len(values)//2]
    second_half = values[len(values)//2:]
    if not first_half or not second_half:
        return "insufficient_data"
    avg_first = statistics.mean(first_half)
    avg_second = statistics.mean(second_half)
    delta = avg_second - avg_first
    if delta > 1.0:
        return "improving"
    elif delta < -1.0:
        return "declining"
    else:
        return "stable"

def main():
    # Load input files
    decision_trace = load_json('logs/decision_trace.json') or {'decisions': []}
    ghs_data = load_json('reports/governance_health.json') or {}
    msi_data = load_json('reports/meta_stability.json') or {}
    coherence_data = load_json('reports/governance_coherence.json') or {}
    equilibrium_data = load_json('reports/governance_equilibrium.json') or {}
    
    # Extract decision history (last 50 cycles)
    decisions = decision_trace.get('decisions', [])[-50:]
    
    # Extract historical snapshots from equilibrium data
    equilibrium_history = equilibrium_data.get('history', [])[-50:]
    
    # Current values
    current_ghs = ghs_data.get('ghs', 0.0) or ghs_data.get('GovernanceHealthScore', 0.0)
    current_msi = msi_data.get('meta_stability_index', 0.0)
    current_coherence = coherence_data.get('coherence_index', 100.0)
    
    # Build time series from available data
    ghs_history = [current_ghs]
    msi_history = [current_msi]
    coherence_history = [current_coherence]
    
    # Extract from equilibrium history if available
    for entry in equilibrium_history:
        if 'snapshots' in entry:
            ghs_history.insert(0, entry['snapshots'].get('ghs', 0.0))
            msi_history.insert(0, entry['snapshots'].get('msi', 0.0))
            coherence_history.insert(0, entry['snapshots'].get('coherence_index', 100.0))
    
    # Compute statistics
    if len(ghs_history) > 1:
        avg_health = statistics.mean(ghs_history)
        var_health = statistics.variance(ghs_history) if len(ghs_history) > 1 else 0.0
    else:
        avg_health = current_ghs
        var_health = 0.0
    
    if len(msi_history) > 1:
        avg_stability = statistics.mean(msi_history)
        var_stability = statistics.variance(msi_history) if len(msi_history) > 1 else 0.0
    else:
        avg_stability = current_msi
        var_stability = 0.0
    
    if len(coherence_history) > 1:
        avg_coherence = statistics.mean(coherence_history)
    else:
        avg_coherence = current_coherence
    
    # Analyze stabilization modes from decisions
    modes = [d.get('stabilization_mode', 'monitor') for d in decisions if 'stabilization_mode' in d]
    if modes:
        mode_counts = Counter(modes)
        dominant_mode = mode_counts.most_common(1)[0][0]
        mode_percentages = {k: round(100 * v / len(modes), 1) for k, v in mode_counts.items()}
    else:
        dominant_mode = "monitor"
        mode_percentages = {"monitor": 100.0}
    
    # Detect recurrent conflicts
    conflict_patterns = []
    
    # Pattern 1: Repeated interventions
    intervention_count = sum(1 for d in decisions if d.get('stabilization_mode') in ['active', 'adaptive'])
    if intervention_count > len(decisions) * 0.3:
        conflict_patterns.append(f"High intervention frequency: {intervention_count}/{len(decisions)} cycles required stabilization")
    
    # Pattern 2: Oscillating modes
    if len(modes) >= 5:
        mode_switches = sum(1 for i in range(1, len(modes)) if modes[i] != modes[i-1])
        if mode_switches > len(modes) * 0.4:
            conflict_patterns.append(f"Mode oscillation detected: {mode_switches} switches in {len(modes)} cycles")
    
    # Pattern 3: Persistent low stability
    low_msi_cycles = sum(1 for m in msi_history if m < 50.0)
    if low_msi_cycles > len(msi_history) * 0.3:
        conflict_patterns.append(f"Persistent low stability: {low_msi_cycles}/{len(msi_history)} cycles below 50% MSI")
    
    # Pattern 4: Recurring coherence drops
    coherence_drops = sum(1 for c in coherence_history if c < 80.0)
    if coherence_drops > len(coherence_history) * 0.2:
        conflict_patterns.append(f"Recurring coherence issues: {coherence_drops}/{len(coherence_history)} cycles below 80%")
    
    # Compute trend directions
    ghs_trend = compute_trend(ghs_history)
    msi_trend = compute_trend(msi_history)
    
    # Overall trend assessment
    if ghs_trend == "improving" and msi_trend == "improving":
        overall_trend = "improving"
    elif ghs_trend == "declining" or msi_trend == "declining":
        overall_trend = "declining"
    else:
        overall_trend = "stable"
    
    # Generate recommendations
    recommendations = []
    if avg_coherence < 80:
        recommendations.append("Consider investigating parameter alignment conflicts")
    if var_stability > 100:
        recommendations.append("High stability variance detected — review adaptive learning rates")
    if intervention_count > len(decisions) * 0.5:
        recommendations.append("Frequent interventions suggest need for policy recalibration")
    if not conflict_patterns:
        recommendations.append("System operating within normal parameters — continue monitoring")
    
    # Build output
    output = {
        'timestamp': datetime.utcnow().isoformat(),
        'summary_period': f"Last {len(decisions)} governance cycles",
        'cycles_analyzed': len(decisions),
        'metrics': {
            'avg_health': round(avg_health, 2),
            'var_health': round(var_health, 2),
            'avg_stability': round(avg_stability, 2),
            'var_stability': round(var_stability, 2),
            'avg_coherence': round(avg_coherence, 2)
        },
        'mode_distribution': mode_percentages,
        'dominant_mode': dominant_mode,
        'recurrent_conflicts': conflict_patterns,
        'trends': {
            'ghs': ghs_trend,
            'msi': msi_trend,
            'overall': overall_trend
        },
        'recommendations': recommendations,
        'data_quality': {
            'ghs_samples': len(ghs_history),
            'msi_samples': len(msi_history),
            'coherence_samples': len(coherence_history),
            'decision_records': len(decisions)
        }
    }
    
    # Write reports/governance_memory.json
    save_json('reports/governance_memory.json', output)
    
    # Update reports/audit_summary.md
    summary_path = 'reports/audit_summary.md'
    if os.path.exists(summary_path):
        with open(summary_path, 'r', encoding='utf-8') as f:
            md = f.read()
    else:
        md = "# Audit Summary\n\n"
    
    start = md.find('<!-- GOVERNANCE_MEMORY:BEGIN -->')
    end = md.find('<!-- GOVERNANCE_MEMORY:END -->')
    
    # Format conflict summary
    if conflict_patterns:
        conflict_summary = f"{len(conflict_patterns)} pattern(s) detected"
    else:
        conflict_summary = "no recurring anomalies"
    
    stable_pct = mode_percentages.get('monitor', 0.0) + mode_percentages.get('adaptive', 0.0)
    
    block = f"""
<!-- GOVERNANCE_MEMORY:BEGIN -->
**Governance Memory Consolidation**

- Period: {output['summary_period']}
- Average Health (GHS): {avg_health:.1f}% (σ²={var_health:.1f})
- Average Stability (MSI): {avg_stability:.1f}% (σ²={var_stability:.1f})
- Average Coherence: {avg_coherence:.1f}%
- Dominant Mode: **{dominant_mode.upper()}**
- Stable Cycles: {stable_pct:.0f}%
- Trend: {overall_trend}
- Recurring Conflicts: {conflict_summary}
- Recommendations: {'; '.join(recommendations[:2]) if recommendations else 'Continue monitoring'}
- Updated: {output['timestamp']}
<!-- GOVERNANCE_MEMORY:END -->
"""
    
    if start != -1 and end != -1:
        md = md[:start] + block + md[end+len('<!-- GOVERNANCE_MEMORY:END -->'):]
    else:
        md += '\n' + block
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(md)
    
    # Print output for CI
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
