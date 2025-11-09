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

    # Reviewer metrics
    ledger = _load_ledger()
    approvals = sum(1 for e in ledger if str(e.get("verdict","")) == "approved")
    total_reviews = len(ledger)
    approval_rate = (approvals/total_reviews*100.0) if total_reviews else 0.0
    # naive turnaround: unavailable without timestamps per pending/open; display total count instead
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

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
  <table>
    <thead><tr><th>Date</th><th>Status</th><th>Passed</th><th>Failed</th><th>Issue</th></tr></thead>
    <tbody>
      {''.join(f'<tr><td>{d}</td><td>{s}</td><td>{p}</td><td>{f}</td><td>' + (f'<a href="{ln}">link</a>' if ln else '-') + '</td></tr>' for d,s,p,f,ln in zip(labels, status, passed, failed, links))}
    </tbody>
  </table>
  <div class="foot">Last update: {now}</div>
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
  drawTS('ts');
  drawPie('pie', {json.dumps(metrics.get('severity_counts', {}))});
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
