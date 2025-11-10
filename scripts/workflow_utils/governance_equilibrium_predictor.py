"""
Governance Equilibrium Predictor
Forecasts whether governance parameters are trending toward equilibrium or divergence.
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

def save_json(path, data):
    """Save data to JSON file."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def compute_slope(values):
    """Compute simple linear slope from list of values."""
    n = len(values)
    if n < 2:
        return 0.0
    # Simple slope: (last - first) / (n - 1)
    return (values[-1] - values[0]) / (n - 1)

def main():
    # Load input files
    coherence_data = load_json('reports/governance_coherence.json') or {}
    msi_data = load_json('reports/meta_stability.json') or {}
    ghs_data = load_json('reports/governance_health.json') or {}
    
    # Load historical equilibrium data for trend analysis
    equilibrium_history = load_json('reports/governance_equilibrium.json') or {}
    history = equilibrium_history.get('history', [])
    
    # Current values
    current_coherence = coherence_data.get('coherence_index', 100.0)
    current_msi = msi_data.get('meta_stability_index', 0.0)
    current_ghs = ghs_data.get('ghs', 0.0) or ghs_data.get('GovernanceHealthScore', 0.0)
    
    # Build rolling history (keep last 5 runs)
    coherence_history = [current_coherence]
    msi_history = [current_msi]
    
    # Extract from past equilibrium records if available
    if history:
        for entry in history[-4:]:  # Get up to 4 previous entries
            coherence_history.insert(0, entry.get('coherence_snapshot', 100.0))
            msi_history.insert(0, entry.get('msi_snapshot', 0.0))
    
    # Compute slopes (trend direction)
    coherence_slope = compute_slope(coherence_history)
    msi_slope = compute_slope(msi_history)
    
    # Stability factor: mean of normalized MSI and coherence
    stability_factor = (current_msi + current_coherence) / 200.0  # Normalize to 0-1
    
    # Trend score: weighted combination of slopes
    trend_score = 0.6 * coherence_slope + 0.4 * msi_slope
    
    # Determine trend direction
    if trend_score > 0.5:
        trend = "converging"
    elif trend_score < -0.5:
        trend = "diverging"
    else:
        trend = "neutral"
    
    # Project equilibrium time (in cycles)
    # How many cycles until coherence reaches 100%?
    if trend_score > 0:
        gap = max(0, 100.0 - current_coherence)
        predicted_cycles = gap / (abs(trend_score) * 10 + 1e-6)
        predicted_cycles = min(predicted_cycles, 999)  # Cap at 999 cycles
    elif trend_score < 0:
        # Diverging: estimate cycles until critical threshold (50%)
        gap = max(0, current_coherence - 50.0)
        predicted_cycles = gap / (abs(trend_score) * 10 + 1e-6)
        predicted_cycles = min(predicted_cycles, 999)
    else:
        predicted_cycles = 999  # Neutral, no convergence predicted
    
    # Confidence based on:
    # - Number of samples (more = higher confidence)
    # - Stability factor (higher = more predictable)
    # - Consistency of trend
    sample_confidence = min(1.0, len(coherence_history) / 5.0)
    trend_confidence = stability_factor
    confidence = (0.5 * sample_confidence + 0.5 * trend_confidence)
    
    # Prepare notes
    if trend == "converging":
        notes = f"Based on coherence + meta-stability trends. System parameters aligning toward equilibrium."
    elif trend == "diverging":
        notes = f"Based on coherence + meta-stability trends. System parameters showing divergent behavior."
    else:
        notes = f"Based on coherence + meta-stability trends. System in neutral state, no clear trend."
    
    # Build output
    output = {
        'timestamp': datetime.utcnow().isoformat(),
        'trend': trend,
        'trend_score': round(trend_score, 3),
        'stability_factor': round(stability_factor, 3),
        'predicted_equilibrium_cycles': round(predicted_cycles, 1),
        'confidence': round(confidence, 2),
        'notes': notes,
        'snapshots': {
            'coherence_index': current_coherence,
            'msi': current_msi,
            'ghs': current_ghs
        },
        'slopes': {
            'coherence_slope': round(coherence_slope, 3),
            'msi_slope': round(msi_slope, 3)
        },
        'history': history[-9:] + [{
            'timestamp': datetime.utcnow().isoformat(),
            'coherence_snapshot': current_coherence,
            'msi_snapshot': current_msi,
            'trend': trend,
            'trend_score': round(trend_score, 3)
        }]  # Keep last 10 entries
    }
    
    # Write reports/governance_equilibrium.json
    save_json('reports/governance_equilibrium.json', output)
    
    # Update reports/audit_summary.md
    summary_path = 'reports/audit_summary.md'
    if os.path.exists(summary_path):
        with open(summary_path, 'r', encoding='utf-8') as f:
            md = f.read()
    else:
        md = "# Audit Summary\n\n"
    
    start = md.find('<!-- GOVERNANCE_EQUILIBRIUM:BEGIN -->')
    end = md.find('<!-- GOVERNANCE_EQUILIBRIUM:END -->')
    
    # Format cycles display
    if predicted_cycles < 100:
        cycles_str = f"~{predicted_cycles:.0f} cycles"
    else:
        cycles_str = ">100 cycles"
    
    block = f"""
<!-- GOVERNANCE_EQUILIBRIUM:BEGIN -->
**Governance Equilibrium Forecast**

- Predicted equilibrium in {cycles_str} (confidence {confidence*100:.0f}%)
- Trend: **{trend.upper()}**
- Trend Score: {trend_score:.3f}
- Stability Factor: {stability_factor:.3f}
- Current Coherence: {current_coherence:.1f}%
- Current MSI: {current_msi:.1f}%
- Notes: {notes}
- Updated: {output['timestamp']}
<!-- GOVERNANCE_EQUILIBRIUM:END -->
"""
    
    if start != -1 and end != -1:
        md = md[:start] + block + md[end+len('<!-- GOVERNANCE_EQUILIBRIUM:END -->'):]
    else:
        md += '\n' + block
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(md)
    
    # Print output for CI
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
