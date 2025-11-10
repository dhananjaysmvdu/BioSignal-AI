"""
Trust Correlation Controller
Automatically tunes governance policy's trust_weight_factor based on measured correlations
between signature verification mode and governance health metrics.
"""
import os
import json
from datetime import datetime

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def main():
    # Load inputs
    trust_corr = load_json('reports/trust_correlation.json')
    policy = load_json('configs/governance_policy.json')
    
    if trust_corr is None:
        print('trust_correlation.json not found, skipping adjustment')
        return
    
    if policy is None:
        policy = {}
    
    # Extract current values
    corr_ghs = trust_corr.get('corr_trust_GHS', 0.0)
    corr_msi = trust_corr.get('corr_trust_MSI', 0.0)
    samples = trust_corr.get('samples', 0)
    confidence = trust_corr.get('confidence', 0.0)
    
    # Average correlation for decision
    avg_corr = (corr_ghs + corr_msi) / 2.0
    
    # Current trust weight factor (default 0.5 if not present)
    current_weight = policy.get('trust_weight_factor', 0.5)
    new_weight = current_weight
    adjustment = 0.0
    reason = "No adjustment (correlation too weak or insufficient confidence)"
    
    # Decision logic
    if abs(avg_corr) < 0.3 or confidence < 0.5:
        # Correlation too weak or confidence too low
        adjustment = 0.0
        reason = f"No adjustment (avg_corr={avg_corr:.2f}, confidence={confidence:.2f})"
    elif avg_corr >= 0.5:
        # Strong positive correlation: increase trust weight
        adjustment = 0.05
        new_weight = min(1.0, current_weight + adjustment)
        reason = f"Strong positive correlation detected (avg_corr={avg_corr:.2f}): increasing trust weight"
    elif avg_corr <= -0.5:
        # Strong negative correlation: decrease trust weight
        adjustment = -0.05
        new_weight = max(0.0, current_weight + adjustment)
        reason = f"Strong negative correlation detected (avg_corr={avg_corr:.2f}): decreasing trust weight"
    
    # Update policy
    policy['trust_weight_factor'] = round(new_weight, 3)
    policy['trust_correlation_last_update'] = datetime.utcnow().isoformat()
    policy['trust_correlation_avg'] = round(avg_corr, 2)
    policy['trust_correlation_confidence'] = round(confidence, 2)
    
    # Save updated policy
    os.makedirs('configs', exist_ok=True)
    save_json('configs/governance_policy.json', policy)
    
    # Update audit_summary.md
    summary_path = 'reports/audit_summary.md'
    if os.path.exists(summary_path):
        with open(summary_path, 'r', encoding='utf-8') as f:
            md = f.read()
        
        start = md.find('<!-- TRUST_CORRELATION_CONTROL:BEGIN -->')
        end = md.find('<!-- TRUST_CORRELATION_CONTROL:END -->')
        
        block = f"""
<!-- TRUST_CORRELATION_CONTROL:BEGIN -->
**Trust Weighting Control**

- Previous trust_weight_factor: {current_weight:.3f}
- New trust_weight_factor: {new_weight:.3f}
- Adjustment: {adjustment:+.3f}
- Average correlation (GHS+MSI): {avg_corr:.2f}
- Confidence: {confidence:.2f}
- Samples: {samples}
- Reason: {reason}
- Updated: {policy.get('trust_correlation_last_update', 'N/A')}
<!-- TRUST_CORRELATION_CONTROL:END -->
"""
        
        if start != -1 and end != -1:
            md = md[:start] + block + md[end+len('<!-- TRUST_CORRELATION_CONTROL:END -->'):]
        else:
            md += '\n' + block
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(md)
    
    # Output summary
    output = {
        'previous_weight': current_weight,
        'new_weight': new_weight,
        'adjustment': adjustment,
        'avg_correlation': avg_corr,
        'confidence': confidence,
        'reason': reason,
        'timestamp': policy.get('trust_correlation_last_update')
    }
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
