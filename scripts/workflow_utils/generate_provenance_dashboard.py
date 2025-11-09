#!/usr/bin/env python3
"""
Generate an HTML provenance insights dashboard from audit summaries and versions history.
Inputs (read if present):
- reports/audit_summary.md (latest)
- reports/history/versions.json
- past reports/audit_summary*.md files (for trend)
Output:
- reports/provenance_dashboard.html

No external dependencies. Pure Python + inline JS/SVG.
"""
from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime, timezone
from glob import glob
from typing import List, Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPORTS_DIR = os.path.join(ROOT, "reports")
HISTORY_JSON = os.path.join(ROOT, "reports", "history", "versions.json")
LEDGER_JSON = os.path.join(ROOT, "logs", "oversight_ledger.json")
SCORES_JSON = os.path.join(ROOT, "logs", "reviewer_scores.json")

MD_PATTERN = re.compile(r"^\s*-\s*(?P<key>[^:]+):\s*(?P<value>.*)$")
TS_KEYS = {"Timestamp", "timestamp"}
KEY_MAP = {
    "Timestamp": "timestamp",
    "Auditor": "auditor",
    "Commits checked": "checked",
    "Checked": "checked",
    "Passed": "passed",
    "Failed": "failed",
    "Remediated": "remediated",
    "Issue": "issue",
    "Workflow": "workflow",
    "Overall Status": "status",
}

def _parse_md_summary(path: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = MD_PATTERN.match(line.strip())
            if not m:
                continue
            key = m.group("key").strip()
            val = m.group("value").strip()
            key = KEY_MAP.get(key, key)
            data[key] = val
    # normalize numbers
    for k in ("checked", "passed", "failed", "remediated"):
        if k in data:
            try:
                data[k] = int(re.findall(r"\d+", str(data[k]))[0])
            except Exception:
                data[k] = 0
    # normalize timestamp
    ts = data.get("timestamp")
    if ts:
        # accept formats like "2025-11-09 05:00:00 UTC" or ISO-8601
        ts_clean = ts.replace(" UTC", "").replace("T", " ").replace("Z", "")
        try:
            data["_dt"] = datetime.fromisoformat(ts_clean)
        except Exception:
            try:
                data["_dt"] = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
            except Exception:
                data["_dt"] = None
    else:
        data["_dt"] = None
    return data


def _load_history_versions() -> Dict[str, Any]:
    if not os.path.exists(HISTORY_JSON):
        return {}
    try:
        with open(HISTORY_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _load_ledger() -> List[Dict[str, Any]]:
  if not os.path.exists(LEDGER_JSON):
    return []
  try:
    with open(LEDGER_JSON, "r", encoding="utf-8") as f:
      data = json.load(f)
      if isinstance(data, list):
        return data
  except Exception:
    return []
  return []

def _load_scores() -> Dict[str, Any]:
  if not os.path.exists(SCORES_JSON):
    return {}
  try:
    with open(SCORES_JSON, "r", encoding="utf-8") as f:
      return json.load(f)
  except Exception:
    return {}


def _collect_runs() -> List[Dict[str, Any]]:
    paths = []
    # include the canonical summary
    main_md = os.path.join(REPORTS_DIR, "audit_summary.md")
    if os.path.exists(main_md):
        paths.append(main_md)
    # include any historical summaries if user stores versions like audit_summary_*.md
    paths.extend(sorted(glob(os.path.join(REPORTS_DIR, "audit_summary*.md"))))
    # de-dup
    paths = list(dict.fromkeys(paths))
    runs: List[Dict[str, Any]] = []
    for p in paths:
        d = _parse_md_summary(p)
        if d:
            d["_path"] = os.path.relpath(p, ROOT)
            runs.append(d)
    # sort by timestamp if present
    runs.sort(key=lambda x: x.get("_dt") or datetime.min, reverse=False)
    return runs


def _compute_metrics(runs: List[Dict[str, Any]], window: int = 10) -> Dict[str, Any]:
    last = runs[-window:] if runs else []
    total_runs = len(last)
    if total_runs == 0:
        return {
            "pass_rate": 0.0,
            "avg_drift": 0.0,
            "remediation_freq": 0.0,
            "severity_counts": {"PASS": 0, "ATTENTION REQUIRED": 0},
        }
    pass_runs = sum(1 for r in last if str(r.get("status", "")).upper().startswith("PASS"))
    # drift rate = sum(failed)/sum(checked); guard divide by zero
    sum_failed = sum(int(r.get("failed", 0)) for r in last)
    sum_checked = sum(int(r.get("checked", 0)) for r in last)
    avg_drift = (sum_failed / sum_checked) if sum_checked else 0.0
    remediation_runs = sum(1 for r in last if int(r.get("remediated", 0)) > 0)
    severity_counts = {
        "PASS": sum(1 for r in last if str(r.get("status", "")).upper().startswith("PASS")),
        "ATTENTION REQUIRED": sum(1 for r in last if str(r.get("status", "")).upper().startswith("ATTENTION")),
    }
    return {
        "pass_rate": pass_runs / total_runs,
        "avg_drift": avg_drift,
        "remediation_freq": remediation_runs / total_runs,
        "severity_counts": severity_counts,
    }


def _render_html(runs: List[Dict[str, Any]], metrics: Dict[str, Any], history: Dict[str, Any]) -> str:
    # Prepare series
    labels = [ (r.get("_dt") or datetime.min).strftime("%Y-%m-%d") for r in runs ]
    passed = [ int(r.get("passed", 0)) for r in runs ]
    failed = [ int(r.get("failed", 0)) for r in runs ]
    status = [ str(r.get("status", "")) for r in runs ]
    links = [ r.get("issue") or "" for r in runs ]

    sev = metrics.get("severity_counts", {"PASS": 0, "ATTENTION REQUIRED": 0})
    pass_rate = metrics.get("pass_rate", 0.0) * 100.0
    avg_drift = metrics.get("avg_drift", 0.0) * 100.0
    remediation_freq = metrics.get("remediation_freq", 0.0) * 100.0

    # Reviewer metrics & trust index
    ledger = _load_ledger()
    scores = _load_scores()
    approvals = sum(1 for e in ledger if str(e.get("verdict","")) == "approved")
    total_reviews = len(ledger)
    approval_rate = (approvals/total_reviews*100.0) if total_reviews else 0.0
    mean_alignment = 0.0
    if scores:
        vals = [float(v.get("alignment",0.0)) for v in scores.values()]
        mean_alignment = sum(vals)/len(vals) if vals else 0.0
    disagreement_rate = 1.0 - (approval_rate/100.0) if total_reviews else 0.0
    oversight_trust_index = max(0.0, min(1.0, mean_alignment * (1.0 - disagreement_rate))) * 100.0
    # naive turnaround: unavailable without timestamps per pending/open; display total count instead
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Governance Pulse inputs
    # Load current governance health & policy if present
    gh_path = os.path.join(REPORTS_DIR, 'governance_health.json')
    cur_ghs = 0.0
    gh_components = {}
    if os.path.exists(gh_path):
        try:
            with open(gh_path,'r',encoding='utf-8') as f:
                _gh = json.load(f)
            cur_ghs = float(_gh.get('GovernanceHealthScore') or 0.0)
            gh_components = _gh.get('Components', {})
        except Exception:
            pass
    policy_path = os.path.join(ROOT, 'configs', 'governance_policy.json')
    next_audit_date = ''
    confidence_threshold = ''
    audit_freq = ''
    if os.path.exists(policy_path):
        try:
            with open(policy_path,'r',encoding='utf-8') as f:
                pol = json.load(f)
            next_audit_date = pol.get('next_audit_date','')
            confidence_threshold = pol.get('learning_coefficients',{}).get('confidence_weight', pol.get('confidence_threshold'))
            audit_freq = pol.get('audit_frequency','')
        except Exception:
            pass
    # Historical GHS from versions.json if annotated
    gh_history = []  # list of (date, ghs, audit_days)
    versions_path = os.path.join(REPORTS_DIR,'history','versions.json')
    if os.path.exists(versions_path):
        try:
            with open(versions_path,'r',encoding='utf-8') as f:
                vj = json.load(f)
            entries = vj.get('history') or vj.get('versions') or vj.get('entries') or []
            if isinstance(entries,list):
                for e in entries[-30:]:
                    dt = e.get('timestamp') or e.get('date') or ''
                    ghs_val = e.get('ghs') or e.get('GovernanceHealthScore') or None
                    aud = e.get('audit_frequency') or e.get('audit_freq') or ''
                    if ghs_val is not None:
                        days = 0
                        if isinstance(aud,str) and aud.endswith('d'):
                            try:
                                days = int(aud[:-1])
                            except Exception:
                                days = 0
                        gh_history.append((dt[:10], float(ghs_val), days))
        except Exception:
            pass
    if not gh_history:
        gh_history.append((datetime.utcnow().strftime('%Y-%m-%d'), cur_ghs, 0))
    gh_labels = [g[0] for g in gh_history]
    gh_values = [round(g[1],2) for g in gh_history]
    gh_audit_days = [g[2] for g in gh_history]

    # Tiny charting: inline canvas drawing without external libs
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Provenance Insights Dashboard</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
  h1 {{ margin-bottom: 8px; }}
  .kpis {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }}
  .kpi {{ background: #f5f5f5; padding: 12px 16px; border-radius: 8px; min-width: 180px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  canvas {{ width: 100%; height: 300px; border: 1px solid #eee; background: #fff; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; }}
  th {{ background: #fafafa; text-align: left; }}
  .ok {{ color: #0a7; }}
  .warn {{ color: #d33; }}
  .foot {{ margin-top: 16px; color: #666; font-size: 13px; }}
</style>
</head>
<body>
  <h1>Provenance Insights Dashboard</h1>
  <div class="kpis">
    <div class="kpi"><strong>10-run Pass Rate</strong><br>{pass_rate:.1f}%</div>
    <div class="kpi"><strong>Avg Drift Rate</strong><br>{avg_drift:.2f}%</div>
    <div class="kpi"><strong>Remediation Frequency</strong><br>{remediation_freq:.1f}%</div>
    <div class="kpi"><strong>Approval Rate</strong><br>{approval_rate:.1f}% ({total_reviews} reviews)</div>
    <div class="kpi"><strong>Oversight Trust Index</strong><br>{oversight_trust_index:.1f}%</div>
  </div>
  <div class="grid">
    <div>
      <h3>Time-series: Passed vs Failed</h3>
      <canvas id="ts"></canvas>
    </div>
    <div>
      <h3>Severity Breakdown</h3>
      <canvas id="pie"></canvas>
    </div>
  </div>
  <h3 style="margin-top:24px">Audit Runs</h3>
  <h3>Reviewer Alignment</h3>
  <div>
    <canvas id="align"></canvas>
  </div>
  <table>
    <thead><tr><th>Date</th><th>Status</th><th>Passed</th><th>Failed</th><th>Issue</th></tr></thead>
    <tbody>
      {''.join(f'<tr><td>{d}</td><td>{s}</td><td>{p}</td><td>{f}</td><td>' + (f'<a href="{ln}">link</a>' if ln else '-') + '</td></tr>' for d,s,p,f,ln in zip(labels, status, passed, failed, links))}
    </tbody>
  </table>
  <div class="foot">Last update: {now}</div>
  <section id="governance_pulse" style="margin-top:40px">
    <h2>Governance Pulse Over Time</h2>
    <p style="max-width:640px;font-size:14px;color:#444">Composite view of Governance Health Score (GHS) and audit cadence adjustments enabling longitudinal oversight of technical, calibration, ethical trust and operational stability signals.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start;">
      <div>
        <h4>GHS Trend</h4>
        <canvas id="ghsTrend" height="260"></canvas>
      </div>
      <div>
        <h4>Audit Cadence</h4>
        <canvas id="auditCadence" height="260"></canvas>
      </div>
    </div>
    <div style="margin-top:16px;display:flex;align-items:center;gap:32px;flex-wrap:wrap;">
      <div style="position:relative;width:140px;height:140px;">
        <svg width="140" height="140" viewBox="0 0 140 140">
          <circle cx="70" cy="70" r="62" fill="#fff" stroke="#eee" stroke-width="4" />
          <circle id="pulseRing" cx="70" cy="70" r="62" fill="none" stroke="#0a7" stroke-width="6" stroke-linecap="round" stroke-dasharray="390" stroke-dashoffset="0">
            <animate attributeName="stroke-dashoffset" values="0;780;0" dur="6s" repeatCount="indefinite" />
            <animate attributeName="stroke" values="#2cbe4e;#dfb317;#d73a49;#2cbe4e" dur="9s" repeatCount="indefinite" />
          </circle>
          <text x="70" y="64" text-anchor="middle" font-size="12" font-family="Arial" fill="#444">GHS</text>
          <text id="ghsVal" x="70" y="92" text-anchor="middle" font-size="28" font-family="Arial" font-weight="bold" fill="#222">{cur_ghs:.1f}%</text>
        </svg>
      </div>
      <div style="font-size:14px;line-height:1.5;">
        <strong>Current GHS:</strong> {cur_ghs:.1f}%<br>
        <strong>Current Audit Frequency:</strong> {audit_freq or 'n/a'}<br>
        <strong>Confidence Threshold:</strong> {confidence_threshold if confidence_threshold!='' else 'n/a'}<br>
        <strong>Next Audit Scheduled:</strong> {next_audit_date or 'n/a'}<br>
        <em>Updated Components:</em> {', '.join(f"{k}:{v}" for k,v in gh_components.items()) if gh_components else 'n/a'}
      </div>
      <div style="font-size:12px;color:#666;">
        <strong>Legend:</strong><br>
        <span style="color:#2cbe4e">■</span> ≥ 80 Healthy &nbsp; <span style="color:#dfb317">■</span> 60–79 Attention &nbsp; <span style="color:#d73a49">■</span> &lt;60 Critical
      </div>
    </div>
  </section>
<script>
(function() {{
  const labels = {json.dumps(labels)};
  const passed = {json.dumps(passed)};
  const failed = {json.dumps(failed)};
  function drawTS(id) {{
    const c = document.getElementById(id);
    const ctx = c.getContext('2d');
    const W = c.width = c.clientWidth * devicePixelRatio;
    const H = c.height = c.clientHeight * devicePixelRatio;
    ctx.scale(devicePixelRatio, devicePixelRatio);
    const pad = 30;
    const w = c.clientWidth - pad*2, h = c.clientHeight - pad*2;
    const maxY = Math.max(1, ...passed, ...failed);
    function yv(v) {{ return c.clientHeight - pad - (v/maxY)*h; }}
    function xv(i) {{ return pad + (i/(labels.length-1||1))*w; }}
    // axes
    ctx.strokeStyle = '#999'; ctx.lineWidth = 1; ctx.beginPath();
    ctx.moveTo(pad, pad); ctx.lineTo(pad, c.clientHeight - pad); ctx.lineTo(c.clientWidth - pad, c.clientHeight - pad); ctx.stroke();
    // lines
    function line(arr, color) {{
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
      for (let i=0;i<arr.length;i++) {{ const x=xv(i), y=yv(arr[i]); if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y); }}
      ctx.stroke();
    }}
    line(passed, '#0a7');
    line(failed, '#d33');
  }}
  function drawPie(id, data) {{
    const c = document.getElementById(id);
    const ctx = c.getContext('2d');
    const W = c.width = c.clientWidth * devicePixelRatio;
    const H = c.height = c.clientHeight * devicePixelRatio;
    ctx.scale(devicePixelRatio, devicePixelRatio);
    const cx = c.clientWidth/2, cy = c.clientHeight/2, r = Math.min(cx, cy) - 10;
    const total = Object.values(data).reduce((a,b)=>a+b,0) || 1;
    let start = -Math.PI/2;
    const colors = ['#0a7','#d33','#f90','#09f'];
    let i=0;
    for (const [k,v] of Object.entries(data)) {{
      const ang = (v/total)*Math.PI*2;
      ctx.beginPath(); ctx.moveTo(cx,cy); ctx.arc(cx,cy,r,start,start+ang); ctx.closePath();
      ctx.fillStyle = colors[i++%colors.length]; ctx.fill();
    start += ang; }}
    // legend
    let ly = 10; i=0;
    for (const [k,v] of Object.entries(data)) {{
      ctx.fillStyle = colors[i%colors.length]; ctx.fillRect(10, ly, 12, 12);
      ctx.fillStyle = '#222'; ctx.fillText(k+': '+v, 28, ly+11);
      ly += 18; i++;
    }}
  }}
  function drawAlign(id, scores) {{
    const c = document.getElementById(id);
    const ctx = c.getContext('2d');
    const W = c.width = c.clientWidth * devicePixelRatio;
    const H = c.height = c.clientHeight * devicePixelRatio;
    ctx.scale(devicePixelRatio, devicePixelRatio);
    const names = Object.keys(scores);
    const vals = Object.values(scores).map(s=>Number((s.alignment||0)*100));
    const pad = 10, barH = 18, gap = 8, x0 = 120, x1 = c.clientWidth - pad;
    ctx.clearRect(0,0,c.clientWidth,c.clientHeight);
    c.height = (barH+gap)*Math.max(1,names.length) * devicePixelRatio;
    ctx.scale(devicePixelRatio, devicePixelRatio);
    for (let i=0;i<names.length;i++) {{
      const y = pad + i*(barH+gap);
      ctx.fillStyle = '#eee'; ctx.fillRect(x0, y, x1-x0, barH);
      const v = vals[i];
      const w = (x1-x0) * Math.max(0, Math.min(100, v))/100;
      const hue = Math.round((v/100)*120); // 0=red,120=green
  ctx.fillStyle = `hsl(${{hue}},70%,45%)`;
      ctx.fillRect(x0, y, w, barH);
      ctx.fillStyle = '#222'; ctx.fillText(names[i], pad, y+barH-4);
      ctx.fillText(v.toFixed(0)+'%', x0 + w + 6, y+barH-4);
    }}
  }}
  drawTS('ts');
  drawPie('pie', {json.dumps(metrics.get('severity_counts', {}))});
  drawAlign('align', {json.dumps(scores)});
  // Governance Pulse data
  const ghLabels = {json.dumps(gh_labels)};
  const ghValues = {json.dumps(gh_values)};
  const auditDays = {json.dumps(gh_audit_days)};
  function zoneColor(v) {{ return v>=80? '#2cbe4e' : (v>=60? '#dfb317':'#d73a49'); }}
  function drawGhs(id) {{
    const c = document.getElementById(id); if(!c) return; const ctx = c.getContext('2d');
    const W = c.width = c.clientWidth * devicePixelRatio; const H = c.height = c.clientHeight * devicePixelRatio;
    ctx.scale(devicePixelRatio, devicePixelRatio); const pad=30; const w=c.clientWidth-pad*2; const h=c.clientHeight-pad*2;
    const maxY = 100; // % scale
    function xv(i) {{ return pad + (i/(ghLabels.length-1||1))*w; }}
    function yv(v) {{ return c.clientHeight - pad - (v/maxY)*h; }}
    ctx.strokeStyle='#999'; ctx.beginPath(); ctx.moveTo(pad,pad); ctx.lineTo(pad,c.clientHeight-pad); ctx.lineTo(c.clientWidth-pad,c.clientHeight-pad); ctx.stroke();
    // zones (background bands)
    const zones=[80,60,0]; const colors=['#e9f9ee','#fff9e0','#fde9ea'];
    let yPrev=c.clientHeight-pad; for(let zi=0;zi<zones.length;zi++) {{
      const z=zones[zi]; const y=yv(z); ctx.fillStyle=colors[zi]; ctx.fillRect(pad,y,w,yPrev-y); yPrev=y; }}
    // line
    ctx.lineWidth=2; ctx.beginPath(); for(let i=0;i<ghValues.length;i++){{ const x=xv(i), y=yv(ghValues[i]); if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y); }} ctx.strokeStyle='#0366d6'; ctx.stroke();
    // points
    for(let i=0;i<ghValues.length;i++){{ const x=xv(i), y=yv(ghValues[i]); ctx.fillStyle=zoneColor(ghValues[i]); ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2); ctx.fill(); }}
    // x labels (sparse)
    ctx.fillStyle='#222'; ctx.font='11px Arial';
    for(let i=0;i<ghLabels.length;i++){{
      const step = Math.ceil((ghLabels.length/6) || 1);
      if((i % step) === 0 || i === ghLabels.length - 1){{
        ctx.fillText(ghLabels[i], xv(i)-15, c.clientHeight-10);
      }}
    }}
  }}
  function drawAudit(id){{ const c=document.getElementById(id); if(!c) return; const ctx=c.getContext('2d'); const W=c.width=c.clientWidth*devicePixelRatio; const H=c.height=c.clientHeight*devicePixelRatio; ctx.scale(devicePixelRatio,devicePixelRatio); const pad=30; const w=c.clientWidth-pad*2; const h=c.clientHeight-pad*2; const maxY=Math.max(1,...auditDays,14); function xv(i){{ return pad + (i/(auditDays.length-1||1))*w; }} function bh(v){{ return (v/maxY)*h; }} ctx.strokeStyle='#999'; ctx.beginPath(); ctx.moveTo(pad,pad); ctx.lineTo(pad,c.clientHeight-pad); ctx.lineTo(c.clientWidth-pad,c.clientHeight-pad); ctx.stroke(); for(let i=0;i<auditDays.length;i++){{ const v=auditDays[i]; const x=xv(i)-6; const barH=bh(v); ctx.fillStyle='#888'; ctx.fillRect(x, c.clientHeight-pad-barH, 12, barH); }} ctx.fillStyle='#222'; ctx.font='11px Arial'; for(let i=0;i<auditDays.length;i++){{ if(i%Math.ceil(auditDays.length/6||1)==0 || i==auditDays.length-1){{ ctx.fillText(ghLabels[i], xv(i)-15, c.clientHeight-10); }} }} }}
  drawGhs('ghsTrend');
  drawAudit('auditCadence');
  // Pulse ring color adjustment
  const ring=document.getElementById('pulseRing'); if(ring){{ const v={cur_ghs:.1f}; ring.setAttribute('stroke', zoneColor(v)); }}
}})();
</script>
</body>
</html>
"""
    return html


def main() -> int:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    runs = _collect_runs()
    metrics = _compute_metrics(runs, window=10)
    history = _load_history_versions()
    html = _render_html(runs, metrics, history)
    out_path = os.path.join(REPORTS_DIR, "provenance_dashboard.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {os.path.relpath(out_path, ROOT)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
