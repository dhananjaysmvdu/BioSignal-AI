"""
Governance Stabilization Planner
Plans and applies preemptive stabilization actions based on equilibrium forecasts.
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

def parse_audit_frequency(freq_str):
    """Parse audit frequency string like '7d' to days integer."""
    if not freq_str:
        return 7  # Default
    try:
        if isinstance(freq_str, int):
            return freq_str
        if freq_str.endswith('d'):
            return int(freq_str[:-1])
        return int(freq_str)
    except (ValueError, TypeError):
        return 7

def format_audit_frequency(days):
    """Format days as audit frequency string."""
    return f"{days}d"

def main():
    # Load input files
    equilibrium = load_json('reports/governance_equilibrium.json') or {}
    policy = load_json('configs/governance_policy.json') or {}
    msi_data = load_json('reports/meta_stability.json') or {}
    
    # Extract equilibrium forecast
    trend = equilibrium.get('trend', 'neutral')
    confidence = equilibrium.get('confidence', 0.0)
    trend_score = equilibrium.get('trend_score', 0.0)
    predicted_cycles = equilibrium.get('predicted_equilibrium_cycles', 999)
    
    # Extract current policy values
    current_learning_rate = policy.get('learning_rate_factor', 1.0)
    current_audit_freq_str = policy.get('audit_frequency', '7d')
    current_audit_days = parse_audit_frequency(current_audit_freq_str)
    
    # Decision variables
    new_learning_rate = current_learning_rate
    new_audit_days = current_audit_days
    stabilization_mode = "monitor"
    action_taken = "No action"
    rationale = "Monitoring system state"
    
    # Decision logic
    if trend == "diverging" and confidence >= 0.6:
        # System is diverging with high confidence: apply stabilization
        new_learning_rate = max(0.2, current_learning_rate * 0.8)  # Reduce by 20%, min 0.2
        new_audit_days = max(1, int(current_audit_days * 0.5))  # Halve interval (more frequent)
        stabilization_mode = "active"
        action_taken = "Aggressive stabilization"
        rationale = f"Diverging trend detected (score={trend_score:.3f}, confidence={confidence:.2f}). Reducing learning rate and increasing audit frequency to prevent instability."
    
    elif trend == "converging" and confidence >= 0.7:
        # System is converging with high confidence: allow more adaptation
        new_learning_rate = min(1.5, current_learning_rate * 1.1)  # Increase by 10%, max 1.5
        new_audit_days = min(30, int(current_audit_days * 1.5))  # Relax interval (+50%)
        stabilization_mode = "adaptive"
        action_taken = "Adaptive acceleration"
        rationale = f"Converging trend detected (score={trend_score:.3f}, confidence={confidence:.2f}). Increasing learning rate and relaxing audit frequency to accelerate convergence."
    
    elif trend == "neutral" or confidence < 0.6:
        # Neutral or low confidence: maintain current settings
        stabilization_mode = "monitor"
        action_taken = "Maintain current settings"
        rationale = f"Neutral trend or insufficient confidence (trend={trend}, confidence={confidence:.2f}). No adjustments made."
    
    # Update policy
    policy['learning_rate_factor'] = round(new_learning_rate, 3)
    policy['audit_frequency'] = format_audit_frequency(new_audit_days)
    policy['stabilization_mode'] = stabilization_mode
    policy['last_stabilization'] = datetime.utcnow().isoformat()
    policy['stabilization_context'] = {
        'trend': trend,
        'confidence': confidence,
        'trend_score': trend_score,
        'predicted_cycles': predicted_cycles
    }
    
    # Save updated policy
    save_json('configs/governance_policy.json', policy)
    
    # Append to decision trace log
    decision_trace_path = 'logs/decision_trace.json'
    decision_trace = load_json(decision_trace_path) or {'decisions': []}
    
    if not isinstance(decision_trace, dict):
        decision_trace = {'decisions': []}
    if 'decisions' not in decision_trace:
        decision_trace['decisions'] = []
    
    decision_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'type': 'stabilization_planning',
        'trend': trend,
        'confidence': confidence,
        'stabilization_mode': stabilization_mode,
        'action_taken': action_taken,
        'changes': {
            'learning_rate_factor': {
                'previous': current_learning_rate,
                'new': new_learning_rate,
                'delta': round(new_learning_rate - current_learning_rate, 3)
            },
            'audit_frequency': {
                'previous': current_audit_freq_str,
                'new': format_audit_frequency(new_audit_days)
            }
        },
        'rationale': rationale
    }
    
    decision_trace['decisions'].append(decision_entry)
    # Keep last 50 decisions
    decision_trace['decisions'] = decision_trace['decisions'][-50:]
    
    save_json(decision_trace_path, decision_trace)
    
    # Update audit_summary.md
    summary_path = 'reports/audit_summary.md'
    if os.path.exists(summary_path):
        with open(summary_path, 'r', encoding='utf-8') as f:
            md = f.read()
    else:
        md = "# Audit Summary\n\n"
    
    start = md.find('<!-- STABILIZATION_PLANNER:BEGIN -->')
    end = md.find('<!-- STABILIZATION_PLANNER:END -->')
    
    block = f"""
<!-- STABILIZATION_PLANNER:BEGIN -->
**Governance Stabilization Planner**

- Stabilization Mode: **{stabilization_mode.upper()}**
- Action Taken: {action_taken}
- Based on: {trend} forecast (confidence {confidence*100:.0f}%)
- Learning Rate Factor: {current_learning_rate:.3f} → {new_learning_rate:.3f}
- Audit Frequency: {current_audit_freq_str} → {format_audit_frequency(new_audit_days)}
- Rationale: {rationale}
- Updated: {policy['last_stabilization']}
<!-- STABILIZATION_PLANNER:END -->
"""
    
    if start != -1 and end != -1:
        md = md[:start] + block + md[end+len('<!-- STABILIZATION_PLANNER:END -->'):]
    else:
        md += '\n' + block
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(md)
    
    # Output for CI
    output = {
        'stabilization_mode': stabilization_mode,
        'action_taken': action_taken,
        'trend': trend,
        'confidence': confidence,
        'learning_rate_factor': new_learning_rate,
        'audit_frequency': format_audit_frequency(new_audit_days),
        'changes_applied': new_learning_rate != current_learning_rate or new_audit_days != current_audit_days
    }
    
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
