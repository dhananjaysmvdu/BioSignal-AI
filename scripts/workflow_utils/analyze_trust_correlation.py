"""
Analyze Trust–Health Correlation between signature verification mode and governance metrics.
Inputs:
- reports/history/versions.json
- reports/governance_health.json
- reports/meta_stability.json
- Optionally: reports/governance_health_history.json
Outputs:
- reports/trust_correlation.json
- Updates reports/audit_summary.md between TRUST_CORRELATION markers
"""
import os
import json
import math
from datetime import datetime

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def nearest_ts(target, candidates):
    # Find nearest timestamp in candidates to target
    return min(candidates, key=lambda x: abs(x - target)) if candidates else None

def parse_ts(ts):
    # Accepts ISO8601 or '%Y-%m-%d' format
    try:
        return datetime.fromisoformat(ts.replace('Z','').replace('T',' '))
    except Exception:
        try:
            return datetime.strptime(ts, '%Y-%m-%d')
        except Exception:
            return None

def compute_corr(x, y):
    n = len(x)
    if n < 2:
        return 0.0, 0.0
    mean_x = sum(x)/n
    mean_y = sum(y)/n
    cov = sum((xi-mean_x)*(yi-mean_y) for xi,yi in zip(x,y))/n
    std_x = math.sqrt(sum((xi-mean_x)**2 for xi in x)/n)
    std_y = math.sqrt(sum((yi-mean_y)**2 for yi in y)/n)
    if std_x == 0 or std_y == 0:
        return 0.0, 0.0
    corr = cov/(std_x*std_y)
    # Confidence: sqrt(n)/max(10, n) (simple proxy)
    confidence = min(1.0, round(math.sqrt(n)/max(5, n), 2))
    return corr, confidence

def main():
    versions = load_json('reports/history/versions.json')
    ghs = load_json('reports/governance_health.json')
    msi = load_json('reports/meta_stability.json')
    ghs_hist = load_json('reports/governance_health_history.json')
    # Parse history
    if versions is None:
        versions = {}
    history = versions if isinstance(versions, list) else versions.get('history', [])
    ghs_map = {}
    msi_map = {}
    if ghs is None:
        ghs = {}
    if msi is None:
        msi = {}
    if ghs_hist and isinstance(ghs_hist, list):
        for e in ghs_hist:
            ts = parse_ts(e.get('timestamp',''))
            if ts:
                ghs_map[ts] = float(e.get('ghs', ghs.get('ghs', 0.0)))
                msi_map[ts] = float(e.get('msi', msi.get('msi', 0.0)))
    else:
        # Fallback: use latest from ghs/msi
        latest_ts = parse_ts(ghs.get('timestamp','')) or parse_ts(msi.get('timestamp',''))
        if latest_ts:
            ghs_map[latest_ts] = float(ghs.get('ghs', 0.0))
            msi_map[latest_ts] = float(msi.get('msi', 0.0))
    # Pair trust and metrics
    trust_bin = []
    ghs_vals = []
    msi_vals = []
    metric_ts = list(ghs_map.keys())
    for e in history:
        ts = parse_ts(e.get('timestamp',''))
        mode = e.get('signature_verification_mode','')
        if ts and mode:
            nearest = nearest_ts(ts.timestamp(), [t.timestamp() for t in metric_ts])
            if nearest is not None:
                nearest_dt = [t for t in metric_ts if t.timestamp()==nearest][0]
                trust_bin.append(1 if mode=='full' else 0)
                ghs_vals.append(ghs_map[nearest_dt])
                msi_vals.append(msi_map[nearest_dt])
    samples = len(trust_bin)
    if samples < 5:
        corr_trust_GHS, conf_GHS = 0.0, 0.0
        corr_trust_MSI, conf_MSI = 0.0, 0.0
        confidence = 0.0
        interp = "Not enough data to compute correlation. Neutral output."
    else:
        corr_trust_GHS, conf_GHS = compute_corr(trust_bin, ghs_vals)
        corr_trust_MSI, conf_MSI = compute_corr(trust_bin, msi_vals)
        confidence = round((conf_GHS+conf_MSI)/2,2)
        interp = "Strong positive correlation: Full verification tends to coincide with higher governance health and stability." if min(corr_trust_GHS, corr_trust_MSI)>0.5 else (
            "Weak or neutral correlation detected." if max(abs(corr_trust_GHS), abs(corr_trust_MSI))<0.3 else (
            "Negative correlation: Full verification does not align with governance health/stability." if min(corr_trust_GHS, corr_trust_MSI)<-0.5 else "Mixed correlation."))
    out = {
        "timestamp": datetime.utcnow().isoformat(),
        "corr_trust_GHS": round(corr_trust_GHS,2),
        "corr_trust_MSI": round(corr_trust_MSI,2),
        "samples": samples,
        "confidence": confidence,
        "interpretation": interp
    }
    # Write output
    with open('reports/trust_correlation.json','w',encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    # Update audit_summary.md
    summary_path = 'reports/audit_summary.md'
    if os.path.exists(summary_path):
        with open(summary_path,'r',encoding='utf-8') as f:
            md = f.read()
        start = md.find('<!-- TRUST_CORRELATION:BEGIN -->')
        end = md.find('<!-- TRUST_CORRELATION:END -->')
        block = f"""
<!-- TRUST_CORRELATION:BEGIN -->
**Trust–Health Correlation Analysis**

- Correlation (Trust vs GHS): {out['corr_trust_GHS']}
- Correlation (Trust vs MSI): {out['corr_trust_MSI']}
- Samples: {out['samples']}
- Confidence: {out['confidence']}
- Interpretation: {out['interpretation']}
<!-- TRUST_CORRELATION:END -->
"""
        if start!=-1 and end!=-1:
            md = md[:start]+block+md[end+len('<!-- TRUST_CORRELATION:END -->'):]
        else:
            md += '\n'+block
        with open(summary_path,'w',encoding='utf-8') as f:
            f.write(md)
if __name__ == '__main__':
    main()
