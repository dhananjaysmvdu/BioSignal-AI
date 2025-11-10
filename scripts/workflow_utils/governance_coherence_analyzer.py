"""
Governance Coherence Analyzer
Ensures adaptive parameters evolve coherently across subsystems and detects conflicting trends.
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

def get_delta(current, previous, default=0.0):
    """Compute delta between current and previous values."""
    if current is None or previous is None:
        return 0.0
    try:
        return float(current) - float(previous)
    except (TypeError, ValueError):
        return default

def main():
    # Load input files
    policy = load_json('configs/governance_policy.json') or {}
    msi_data = load_json('reports/meta_stability.json') or {}
    trust_corr = load_json('reports/trust_correlation.json') or {}
    ghs_data = load_json('reports/governance_health.json') or {}
    
    # Load historical coherence for delta computation
    prev_coherence = load_json('reports/governance_coherence.json') or {}
    
    # Extract current values
    trust_weight = policy.get('trust_weight_factor', 0.5)
    learning_coeffs = policy.get('learning_coefficients', {})
    confidence_weight = learning_coeffs.get('confidence_weight', 0.0)
    drift_weight = learning_coeffs.get('drift_weight', 0.0)
    human_weight = learning_coeffs.get('human_feedback_weight', 0.0)
    
    msi = msi_data.get('meta_stability_index', 0.0)
    ghs = ghs_data.get('ghs', 0.0) or ghs_data.get('GovernanceHealthScore', 0.0)
    correlation = trust_corr.get('corr_trust_GHS', 0.0)
    
    # Extract previous values for delta computation
    prev_vals = prev_coherence.get('snapshot', {})
    prev_trust = prev_vals.get('trust_weight_factor', trust_weight)
    prev_confidence = prev_vals.get('confidence_weight', confidence_weight)
    prev_drift = prev_vals.get('drift_weight', drift_weight)
    prev_human = prev_vals.get('human_feedback_weight', human_weight)
    prev_msi = prev_vals.get('msi', msi)
    prev_ghs = prev_vals.get('ghs', ghs)
    
    # Compute deltas
    delta_trust = get_delta(trust_weight, prev_trust)
    delta_confidence = get_delta(confidence_weight, prev_confidence)
    delta_drift = get_delta(drift_weight, prev_drift)
    delta_human = get_delta(human_weight, prev_human)
    delta_msi = get_delta(msi, prev_msi)
    delta_ghs = get_delta(ghs, prev_ghs)
    
    # Coherence rules evaluation
    rules = []
    coherent_count = 0
    conflict_count = 0
    
    # Rule 1: trust and confidence should move in same direction when correlation > 0
    if correlation > 0:
        same_direction = (delta_trust * delta_confidence >= 0) or (abs(delta_trust) < 0.01 and abs(delta_confidence) < 0.01)
        rules.append({
            'rule': 'trust_confidence_alignment',
            'description': 'Trust and confidence should move together when correlation > 0',
            'coherent': same_direction,
            'details': f'Δtrust={delta_trust:.3f}, Δconfidence={delta_confidence:.3f}, correlation={correlation:.2f}'
        })
        if same_direction:
            coherent_count += 1
        else:
            conflict_count += 1
    
    # Rule 2: drift weight should decrease if stability (MSI) is rising
    if delta_msi > 0.5:  # Stability improving
        drift_decreasing = delta_drift <= 0.01
        rules.append({
            'rule': 'stability_drift_inverse',
            'description': 'Drift weight should decrease when stability rises',
            'coherent': drift_decreasing,
            'details': f'ΔMSI={delta_msi:.2f}, Δdrift={delta_drift:.3f}'
        })
        if drift_decreasing:
            coherent_count += 1
        else:
            conflict_count += 1
    
    # Rule 3: human_feedback_weight should not rise while trust_weight_factor is falling
    if delta_trust < -0.01:  # Trust decreasing
        human_not_rising = delta_human <= 0.01
        rules.append({
            'rule': 'trust_human_conflict',
            'description': 'Human feedback weight should not increase when trust decreases',
            'coherent': human_not_rising,
            'details': f'Δtrust={delta_trust:.3f}, Δhuman={delta_human:.3f}'
        })
        if human_not_rising:
            coherent_count += 1
        else:
            conflict_count += 1
    
    # Rule 4: GHS and confidence should align (positive GHS trend → confidence can rise)
    if abs(delta_ghs) > 0.5:
        ghs_conf_aligned = (delta_ghs * delta_confidence >= 0) or abs(delta_confidence) < 0.01
        rules.append({
            'rule': 'ghs_confidence_alignment',
            'description': 'GHS and confidence trends should align',
            'coherent': ghs_conf_aligned,
            'details': f'ΔGHS={delta_ghs:.2f}, Δconfidence={delta_confidence:.3f}'
        })
        if ghs_conf_aligned:
            coherent_count += 1
        else:
            conflict_count += 1
    
    # Compute coherence index
    total_rules = coherent_count + conflict_count
    if total_rules == 0:
        coherence_index = 100.0
        status = 'Stable'
    else:
        coherence_index = (coherent_count / total_rules) * 100.0
        if coherence_index >= 80:
            status = 'Stable'
        elif coherence_index >= 50:
            status = 'Mild Conflict'
        else:
            status = 'Severe Conflict'
    
    # Prepare output
    output = {
        'timestamp': datetime.utcnow().isoformat(),
        'coherence_index': round(coherence_index, 1),
        'status': status,
        'coherent_rules': coherent_count,
        'conflicting_rules': conflict_count,
        'total_rules_evaluated': total_rules,
        'rules': rules,
        'deltas': {
            'trust_weight_factor': round(delta_trust, 3),
            'confidence_weight': round(delta_confidence, 3),
            'drift_weight': round(delta_drift, 3),
            'human_feedback_weight': round(delta_human, 3),
            'msi': round(delta_msi, 2),
            'ghs': round(delta_ghs, 2)
        },
        'snapshot': {
            'trust_weight_factor': trust_weight,
            'confidence_weight': confidence_weight,
            'drift_weight': drift_weight,
            'human_feedback_weight': human_weight,
            'msi': msi,
            'ghs': ghs
        }
    }
    
    # Write reports/governance_coherence.json
    save_json('reports/governance_coherence.json', output)
    
    # Update reports/audit_summary.md
    summary_path = 'reports/audit_summary.md'
    if os.path.exists(summary_path):
        with open(summary_path, 'r', encoding='utf-8') as f:
            md = f.read()
    else:
        md = "# Audit Summary\n\n"
    
    start = md.find('<!-- GOVERNANCE_COHERENCE:BEGIN -->')
    end = md.find('<!-- GOVERNANCE_COHERENCE:END -->')
    
    block = f"""
<!-- GOVERNANCE_COHERENCE:BEGIN -->
**Governance Coherence Analysis**

- Coherence Index: {coherence_index:.1f}%
- Status: {status}
- Coherent Rules: {coherent_count}
- Conflicting Rules: {conflict_count}
- Total Rules Evaluated: {total_rules}
- Updated: {output['timestamp']}
<!-- GOVERNANCE_COHERENCE:END -->
"""
    
    if start != -1 and end != -1:
        md = md[:start] + block + md[end+len('<!-- GOVERNANCE_COHERENCE:END -->'):]
    else:
        md += '\n' + block
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(md)
    
    # Print output for CI
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
