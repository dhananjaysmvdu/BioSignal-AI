"""
Governance Regime Stability Monitor
Generates stability gauge, raises alerts on RSI degradation, updates audit summary markers.
Always exits 0.
"""
import os
import json
from datetime import datetime

HISTORY_PATH = 'logs/regime_stability_history.json'
GAUGE_PATH = 'reports/regime_stability_gauge.html'
SUMMARY_PATH = 'reports/audit_summary.md'
STABILITY_JSON = 'reports/regime_stability.json'


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def append_history(rsi):
    hist = load_json(HISTORY_PATH)
    if not isinstance(hist, dict) or 'rsi' not in hist:
        hist = {'rsi': []}
    hist['rsi'].append({'timestamp': datetime.utcnow().isoformat(), 'value': rsi})
    # Limit size to last 100 entries
    if len(hist['rsi']) > 100:
        hist['rsi'] = hist['rsi'][-100:]
    save_json(HISTORY_PATH, hist)
    return hist


def classify(rsi: float):
    if rsi < 50:
        return 'Critical Instability'
    if rsi < 80:
        return 'Moderate Volatility'
    return 'Stable Regime'


def trend_arrow(hist):
    values = [e['value'] for e in hist.get('rsi', [])][-3:]
    if len(values) < 2:
        return '→'
    delta = values[-1] - values[-2]
    if delta > 2:
        return '↑'
    if delta < -2:
        return '↓'
    return '→'


def build_gauge_html(rsi: float, status: str, arrow: str):
        # Use a format template with doubled braces for literal JS braces.
        template = """<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'/>
<title>Regime Stability Gauge</title>
<style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    h1 {{ font-size: 20px; margin-bottom: 8px; }}
    .status {{ font-size: 16px; margin-top: 8px; }}
    canvas {{ max-width: 320px; }}
</style>
</head>
<body>
<h1>Regime Stability Gauge</h1>
<canvas id='gauge' width='320' height='320'></canvas>
<div class='status'>RSI: <strong>{rsi_val}%</strong> {arrow} — {status}</div>
<script>
const rsi = {rsi_val};
const canvas = document.getElementById('gauge');
const ctx = canvas.getContext('2d');
const cx = canvas.width/2; const cy = canvas.height/2; const radius = 130;
ctx.clearRect(0,0,canvas.width,canvas.height);
ctx.lineWidth = 26;
function arc(fromPct,toPct,color){{
    const start = Math.PI * (1 + fromPct);
    const end = Math.PI * (1 + toPct);
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, start, end, false);
    ctx.stroke();
}}
// Zones
arc(0,0.50,'#e53935'); // red
arc(0.50,0.80,'#fdd835'); // yellow
arc(0.80,1.0,'#43a047'); // green
// Needle
const needlePct = Math.min(1, Math.max(0, rsi/100));
const ang = Math.PI * (1 + needlePct);
ctx.strokeStyle='#000';
ctx.lineWidth=4;
ctx.beginPath();
ctx.moveTo(cx, cy);
ctx.lineTo(cx + radius * Math.cos(ang), cy + radius * Math.sin(ang));
ctx.stroke();
// Center
ctx.fillStyle='#000'; ctx.beginPath(); ctx.arc(cx, cy, 8, 0, 2*Math.PI); ctx.fill();
ctx.font='16px Arial'; ctx.textAlign='center'; ctx.fillText(rsi.toFixed(1)+'%', cx, cy+60);
</script>
</body>
</html>
"""
        return template.format(rsi_val=f"{rsi:.2f}", arrow=arrow, status=status)


def update_summary(rsi: float, status: str):
    if os.path.exists(SUMMARY_PATH):
        with open(SUMMARY_PATH, 'r', encoding='utf-8') as f:
            md = f.read()
    else:
        md = '# Audit Summary\n\n'
    start = md.find('<!-- REGIME_ALERT:BEGIN -->')
    end = md.find('<!-- REGIME_ALERT:END -->')
    alert_line = ''
    if status == 'Critical Instability':
        alert_line = f"⚠️ Regime Alert: Stability dropped to {rsi:.0f}% — Critical instability detected."
    elif status == 'Moderate Volatility':
        alert_line = f"⚠️ Regime Alert: Stability at {rsi:.0f}% — Moderate volatility observed."
    else:
        alert_line = f"✅ Regime Stable: RSI {rsi:.0f}% — No alert triggered."
    block = f"\n<!-- REGIME_ALERT:BEGIN -->\n{alert_line}\n<!-- REGIME_ALERT:END -->\n"
    if start != -1 and end != -1:
        md = md[:start] + block + md[end+len('<!-- REGIME_ALERT:END -->'):]
    else:
        md += '\n' + block
    with open(SUMMARY_PATH, 'w', encoding='utf-8') as f:
        f.write(md)


def main():
    try:
        data = load_json(STABILITY_JSON) or {}
        rsi = float(data.get('stability_index', 0.0) or 0.0)
        status = classify(rsi)
        hist = append_history(rsi)
        arrow = trend_arrow(hist)
        html = build_gauge_html(rsi, status, arrow)
        os.makedirs(os.path.dirname(GAUGE_PATH), exist_ok=True)
        with open(GAUGE_PATH, 'w', encoding='utf-8') as f:
            f.write(html)
        update_summary(rsi, status)
        print(json.dumps({'rsi': rsi, 'status': status}, indent=2))
    except Exception:
        print(json.dumps({'rsi': 0, 'status': 'Unknown'}, indent=2))

if __name__ == '__main__':
    main()
