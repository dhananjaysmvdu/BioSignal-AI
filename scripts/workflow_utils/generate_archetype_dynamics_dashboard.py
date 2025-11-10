"""
Generate Archetype Dynamics Dashboard
Creates an HTML dashboard (no external libs) visualizing:
- Transition matrix heatmap
- Dwell duration bar chart (avg cycles per archetype)
- Timeline flow of archetype sequence
- Summary panel with key stats
Also updates reports/audit_summary.md between ARCHETYPE_DYNAMICS markers.
Always exits 0.
"""
import os
import json
from datetime import datetime
from collections import Counter


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_text(path, text):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def compute_sequence_stats(history):
    entries = (history or {}).get('entries', [])
    seq = [e.get('archetype', 'Unknown Archetype') for e in entries]
    confs = [int(e.get('confidence', 0) or 0) for e in entries]
    total_transitions = sum(1 for i in range(1, len(seq)) if seq[i] != seq[i-1])
    # Most frequent path across all changes (a!=b)
    pairs = [(a, b) for a, b in zip(seq[:-1], seq[1:]) if a != b]
    pair_counter = Counter(pairs)
    if pair_counter:
        (p_from, p_to), p_count = pair_counter.most_common(1)[0]
        p_prob = (p_count / len(pairs)) if pairs else 0.0
        dominant_path = {'from': p_from, 'to': p_to, 'count': p_count, 'p': round(p_prob, 2)}
    else:
        dominant_path = {'from': 'N/A', 'to': 'N/A', 'count': 0, 'p': 0.0}
    # Mean dwell time = average run length over runs
    if seq:
        run_len = 1
        runs = []
        for i in range(1, len(seq)):
            if seq[i] == seq[i-1]:
                run_len += 1
            else:
                runs.append(run_len)
                run_len = 1
        runs.append(run_len)
        mean_dwell = sum(runs) / len(runs)
    else:
        mean_dwell = 0.0
    return {
        'sequence': seq,
        'confidences': confs,
        'total_transitions': total_transitions,
        'dominant_path': dominant_path,
        'mean_dwell': round(mean_dwell, 2)
    }


def build_html(transitions, history_stats):
    counts = (transitions or {}).get('transition_counts', {})
    probs = (transitions or {}).get('transition_probabilities_pct', {})
    dwell_avg = (transitions or {}).get('dwell_time_avg_cycles', {})
    last_transition = (transitions or {}).get('last_transition', {})

    labels = sorted({*counts.keys(), *probs.keys(), *dwell_avg.keys()}) or ['Unknown Archetype']

    # Matrix as 2D array aligned with labels
    size = len(labels)
    matrix_counts = [[int(counts.get(a, {}).get(b, 0) or 0) for b in labels] for a in labels]
    matrix_probs = [[float(probs.get(a, {}).get(b, 0.0) or 0.0) for b in labels] for a in labels]

    dwell_list = [{'name': l, 'avg': float(dwell_avg.get(l, 0.0) or 0.0)} for l in labels]
    seq = history_stats['sequence']

    # Inline CSS & JS, draw on Canvas
    data_json = json.dumps({
        'labels': labels,
        'matrix_counts': matrix_counts,
        'matrix_probs': matrix_probs,
        'dwell': dwell_list,
        'sequence': seq
    })

    dominant = history_stats['dominant_path']
    total_transitions = history_stats['total_transitions']
    mean_dwell = history_stats['mean_dwell']
    latest_conf = int(last_transition.get('confidence', 0) or 0)
    latest_from = last_transition.get('from', 'N/A')
    latest_to = last_transition.get('to', 'N/A')

    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>Archetype Dynamics Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    h1 {{ margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; grid-gap: 24px; }}
    .panel {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; }}
    .panel h2 {{ margin: 0 0 8px 0; font-size: 16px; }}
    canvas {{ border: 1px solid #eee; border-radius: 4px; }}
    .summary p {{ margin: 4px 0; }}
    .footer {{ color: #666; font-size: 12px; margin-top: 24px; }}
  </style>
</head>
<body>
  <h1>Archetype Dynamics Dashboard</h1>
  <div class=\"summary panel\">
    <h2>Summary</h2>
    <p>Total transitions: <strong>{total_transitions}</strong></p>
    <p>Dominant path: <strong>{dominant['from']} → {dominant['to']}</strong> (p={dominant['p']:.2f})</p>
    <p>Mean dwell time: <strong>{mean_dwell}</strong> cycles</p>
    <p>Latest: <strong>{latest_from} → {latest_to}</strong> (confidence {latest_conf}%)</p>
  </div>

  <div class=\"grid\">
    <div class=\"panel\">
      <h2>Transition Matrix Heatmap (probabilities %)</h2>
      <canvas id=\"matrix\" width=600 height=600></canvas>
    </div>
    <div class=\"panel\">
      <h2>Dwell Duration (avg cycles)</h2>
      <canvas id=\"dwell\" width=600 height=600></canvas>
    </div>
  </div>

  <div class=\"panel\" style=\"margin-top: 24px;\">
    <h2>Timeline Flow</h2>
    <canvas id=\"timeline\" width=1200 height=120></canvas>
  </div>

  <div class=\"footer\">Generated: {datetime.utcnow().isoformat()}</div>

<script>
const DATA = {data_json};

function drawMatrix(canvasId) {{
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext('2d');
  const labels = DATA.labels;
  const M = DATA.matrix_probs;
  const n = labels.length;
  const margin = 120;
  const cell = Math.floor((canvas.width - margin - 20) / n);
  const size = Math.min(cell, Math.floor((canvas.height - margin - 20) / n));
  // background
  ctx.fillStyle = '#fff'; ctx.fillRect(0,0,canvas.width,canvas.height);
  // axis labels
  ctx.fillStyle = '#000';
  ctx.font = '12px Arial';
  for (let i=0;i<n;i++) {{
    ctx.save();
    ctx.translate(margin + i*size + size/2, margin - 10);
    ctx.rotate(-Math.PI/4);
    ctx.textAlign = 'right';
    ctx.fillText(labels[i], 0, 0);
    ctx.restore();
  }}
  for (let j=0;j<n;j++) {{
    ctx.textAlign = 'right';
    ctx.fillText(labels[j], margin - 10, margin + j*size + size/2);
  }}
  // cells
  for (let r=0;r<n;r++) {{
    for (let c=0;c<n;c++) {{
      const v = M[r][c];
      const hue = 220; // blue scale
      const light = 95 - Math.min(90, v*0.9); // darker for higher
  ctx.fillStyle = `hsl(${{hue}}, 70%, ${{light}}%)`;
      ctx.fillRect(margin + c*size, margin + r*size, size-1, size-1);
      // value
      ctx.fillStyle = v > 50 ? '#fff' : '#000';
      ctx.font = 'bold 11px Arial';
      ctx.textAlign = 'center';
      ctx.fillText(v.toFixed(1), margin + c*size + size/2, margin + r*size + size/2 + 4);
    }}
  }}
}}

function drawBars(canvasId) {{
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext('2d');
  const items = DATA.dwell.slice().sort((a,b)=>b.avg - a.avg);
  const margin = 160;
  const row = 28;
  const height = Math.max(canvas.height, items.length*row + 40);
  canvas.height = height;
  ctx.fillStyle = '#fff'; ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle = '#000'; ctx.font = '12px Arial';
  ctx.fillText('Avg cycles', canvas.width - 80, 20);
  for (let i=0;i<items.length;i++) {{
    const y = 30 + i*row;
    ctx.fillStyle = '#000';
    ctx.textAlign = 'right';
    ctx.fillText(items[i].name, margin - 10, y + 10);
    // bar
    const maxVal = Math.max(...items.map(d=>d.avg), 1);
    const w = (canvas.width - margin - 40) * (items[i].avg / maxVal);
    ctx.fillStyle = '#4CAF50';
    ctx.fillRect(margin, y, w, 16);
    ctx.fillStyle = '#000';
    ctx.textAlign = 'left';
    ctx.fillText(items[i].avg.toFixed(2), margin + w + 6, y + 12);
  }}
}}

function colorForLabel(label) {{
  // hash to color
  let h = 0; for (let i=0;i<label.length;i++) h = (h*31 + label.charCodeAt(i))>>>0;
  const hue = h % 360; return `hsl(${{hue}},65%,60%)`;
}}

function drawTimeline(canvasId) {{
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext('2d');
  const seq = DATA.sequence;
  if (seq.length === 0) {{
    ctx.fillText('No history available', 10, 20);
    return;
  }}
  const w = canvas.width - 20; const h = canvas.height - 40; const x0 = 10; const y = 40;
  // compute runs
  let runs = [];
  let cur = seq[0], len = 1;
  for (let i=1;i<seq.length;i++) {{
    if (seq[i] === cur) len++; else {{ runs.push([cur,len]); cur = seq[i]; len = 1; }}
  }}
  runs.push([cur,len]);
  const total = runs.reduce((a,b)=>a+b[1],0);
  let x = x0;
  for (const [label,len] of runs) {{
    const ww = Math.max(10, Math.round(w * (len/total)));
    ctx.fillStyle = colorForLabel(label);
    ctx.fillRect(x, y, ww, 30);
    ctx.fillStyle = '#000'; ctx.font = '12px Arial'; ctx.textAlign = 'center';
    ctx.fillText(label, x + ww/2, y + 20);
    x += ww + 2;
  }}
}}

(function init() {{
  drawMatrix('matrix');
  drawBars('dwell');
  drawTimeline('timeline');
}})();
</script>
</body>
</html>
"""
    return html


def main():
    try:
        transitions = load_json('reports/archetype_transitions.json') or {}
        history = load_json('logs/archetype_history.json') or {'entries': []}
        stats = compute_sequence_stats(history)

        html = build_html(transitions, stats)
        save_text('reports/archetype_dynamics_dashboard.html', html)

        # Update summary
        summary_path = 'reports/audit_summary.md'
        try:
            if os.path.exists(summary_path):
                with open(summary_path, 'r', encoding='utf-8') as f:
                    md = f.read()
            else:
                md = '# Audit Summary\n\n'
            start = md.find('<!-- ARCHETYPE_DYNAMICS:BEGIN -->')
            end = md.find('<!-- ARCHETYPE_DYNAMICS:END -->')

            dom = stats['dominant_path']
            line = (
                f"🧭 Archetype Dynamics: {stats['total_transitions']} total transitions, "
                f"dominant path {dom['from']} → {dom['to']} (p={dom['p']:.2f})."
            )
            block = f"\n<!-- ARCHETYPE_DYNAMICS:BEGIN -->\n{line}\n<!-- ARCHETYPE_DYNAMICS:END -->\n"
            if start != -1 and end != -1:
                md = md[:start] + block + md[end+len('<!-- ARCHETYPE_DYNAMICS:END -->'):]
            else:
                md += '\n' + block
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(md)
        except Exception:
            pass

        # Print small JSON for CI
        print(json.dumps({
            'transitions': stats['total_transitions'],
            'dominant_path': f"{stats['dominant_path']['from']} → {stats['dominant_path']['to']}",
            'p': stats['dominant_path']['p']
        }, indent=2))
    except Exception:
        print(json.dumps({'transitions': 0, 'dominant_path': 'N/A', 'p': 0.0}, indent=2))


if __name__ == '__main__':
    main()
