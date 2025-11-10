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
    # normalized value for embed
    cur_ghs_val = float(cur_ghs) if isinstance(cur_ghs, (int,float)) else 0.0
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
    coef_history = []  # list of (date, conf_w, drift_w, human_w)
    versions_path = os.path.join(REPORTS_DIR,'history','versions.json')
    if os.path.exists(versions_path):
        try:
            with open(versions_path,'r',encoding='utf-8') as f:
                vj = json.load(f)
            if isinstance(vj, list):
                entries = vj
            else:
                entries = vj.get('history') or vj.get('versions') or vj.get('entries') or []
            if isinstance(entries,list):
                # keep last 30 and ensure order oldest->newest for plotting
                entries = entries[-30:]
                for e in entries:
                    dt = (e.get('timestamp') or e.get('date') or '')
                    ghs_val = e.get('ghs') or e.get('GovernanceHealthScore') or None
                    aud = e.get('audit_frequency') or e.get('audit_freq') or ''
                    if ghs_val is not None:
                        days = 0
                        if isinstance(aud,str) and aud.endswith('d'):
                            try:
                                days = int(aud[:-1])
                            except Exception:
                                days = 0
                        date_str = str(dt)[:10]
                        gh_history.append((date_str, float(ghs_val), days))
                        # pull coefficients if present
                        cw = e.get('confidence_weight')
                        dw = e.get('drift_weight')
                        hw = e.get('human_feedback_weight')
                        if cw is not None or dw is not None or hw is not None:
                            try:
                                coef_history.append((date_str, float(cw or 0.0), float(dw or 0.0), float(hw or 0.0)))
                            except Exception:
                                pass
        except Exception:
            pass
    if not gh_history:
        gh_history.append((datetime.utcnow().strftime('%Y-%m-%d'), cur_ghs_val, 0))
    gh_labels = [g[0] for g in gh_history]
    gh_values = [round(g[1],2) for g in gh_history]
    gh_audit_days = [g[2] for g in gh_history]
    # Align coef history to labels; if missing, try to infer from policy
    if not coef_history:
        # Fallback single point from current policy values if available
        try:
            coef_history = [(gh_labels[-1] if gh_labels else datetime.utcnow().strftime('%Y-%m-%d'),
                             float(confidence_threshold) if isinstance(confidence_threshold,(int,float,str)) else 0.0,
                             0.0,
                             0.0)]
        except Exception:
            coef_history = []
    coef_labels = [c[0] for c in coef_history]
    coef_conf = [round(float(c[1]),4) for c in coef_history]
    coef_drift = [round(float(c[2]),4) for c in coef_history]
    coef_human = [round(float(c[3]),4) for c in coef_history]

    # Meta-stability gauge data
    meta_stability_path = os.path.join(REPORTS_DIR, 'meta_stability.json')
    meta_stability_index = 0.0
    var_conf_msi = 0.0
    var_drift_msi = 0.0
    var_human_msi = 0.0
    meta_ts = ''
    if os.path.exists(meta_stability_path):
        try:
            with open(meta_stability_path, 'r', encoding='utf-8') as f:
                msi_data = json.load(f)
            meta_stability_index = float(msi_data.get('meta_stability_index', 0.0))
            var_conf_msi = float(msi_data.get('variance_conf', 0.0))
            var_drift_msi = float(msi_data.get('variance_drift', 0.0))
            var_human_msi = float(msi_data.get('variance_human', 0.0))
            meta_ts = msi_data.get('timestamp', '')
        except Exception:
            pass

    # Predictive Adaptation Insights data
    adapt_plan_path = os.path.join(REPORTS_DIR, 'adaptation_plan.json')
    causal_path = os.path.join(REPORTS_DIR, 'causal_influence.json')
    predicted_improvement = 0.0
    plan_conf_level = 0
    proposed_coeffs = {
        'confidence_weight': coef_conf[-1] if coef_conf else 0.0,
        'drift_weight': coef_drift[-1] if coef_drift else 0.0,
        'human_feedback_weight': coef_human[-1] if coef_human else 0.0,
    }
    predictive_ts = ''
    if os.path.exists(adapt_plan_path):
        try:
            with open(adapt_plan_path, 'r', encoding='utf-8') as f:
                ap = json.load(f)
            predicted_improvement = float(ap.get('predicted_improvement_percent', 0.0))
            plan_conf_level = int(ap.get('confidence_level', 0) or 0)
            p = ap.get('proposed_coefficients') or {}
            for k in ('confidence_weight','drift_weight','human_feedback_weight'):
                if k in p:
                    try:
                        proposed_coeffs[k] = float(p[k])
                    except Exception:
                        pass
            predictive_ts = ap.get('timestamp', '')
        except Exception:
            pass
    influence_labels = ['Confidence','Drift','Human']
    influence_values = [0.0, 0.0, 0.0]
    if os.path.exists(causal_path):
        try:
            with open(causal_path, 'r', encoding='utf-8') as f:
                ci = json.load(f)
            inf = ci.get('normalized_influence') or {}
            influence_values = [
                float(inf.get('confidence_weight', 0.0)),
                float(inf.get('drift_weight', 0.0)),
                float(inf.get('human_feedback_weight', 0.0)),
            ]
        except Exception:
            pass

    # Verification Mode Timeline Data
    ver_entries = []
    if isinstance(history, list):
        for e in history:
            ts = e.get("timestamp")
            mode = e.get("signature_verification_mode")
            if ts and mode:
                ver_entries.append({"timestamp": ts, "mode": mode})
    total_full = sum(1 for v in ver_entries if v["mode"] == "full")
    total_partial = sum(1 for v in ver_entries if v["mode"] == "partial")
    last_mode = ver_entries[-1]["mode"] if ver_entries else "N/A"
    pct_full = int(round(100 * total_full / max(1, len(ver_entries))))
    ver_labels = [v["timestamp"] for v in ver_entries]
    ver_modes = [v["mode"] for v in ver_entries]

    # Trust–Health Correlation panel data
    trust_corr_path = os.path.join(REPORTS_DIR, 'trust_correlation.json')
    trust_corr = {
        "corr_trust_GHS": 0.0,
        "corr_trust_MSI": 0.0,
        "samples": 0,
        "confidence": 0.0,
        "interpretation": "Not enough data to compute correlation. Neutral output."
    }
    if os.path.exists(trust_corr_path):
        try:
            with open(trust_corr_path, 'r', encoding='utf-8') as f:
                trust_corr.update(json.load(f))
        except Exception:
            pass

    # Tiny charting: inline canvas drawing without external libs
    html = f"""
    <section id="trust_health_correlation" style="margin-top:40px">
      <h2>Trust–Health Correlation</h2>
      <div style="max-width:420px;padding:12px 0;">
        <canvas id="trustCorrChart" height="60" style="width:100%;max-width:420px;"></canvas>
      </div>
      <div style="margin-top:8px;font-size:14px;">
        <span>GHS correlation: <b>{trust_corr['corr_trust_GHS']:.2f}</b></span> &nbsp;|&nbsp; <span>MSI correlation: <b>{trust_corr['corr_trust_MSI']:.2f}</b></span>
      </div>
      <div style="margin-top:4px;font-size:13px;color:#666;">
        Confidence: <b>{trust_corr['confidence']:.2f}</b>
      </div>
      <div style="margin-top:8px;font-size:13px;color:#d33;">
        {'Not enough data yet.' if trust_corr['samples'] < 5 else trust_corr['interpretation']}
      </div>
    </section>
      <section id="verification_mode_timeline" style="margin-top:40px">
        <h2>Verification Mode Timeline</h2>
        <div style="max-width:700px;">
          <canvas id="verModeChart" height="60" style="width:100%;max-width:700px;"></canvas>
        </div>
        <div style="margin-top:12px;">
          <table style="width:auto;min-width:320px;font-size:14px;">
            <tr><th>Total Full Verifications</th><td>{total_full}</td></tr>
          <tr><th>Total Partial Verifications</th><td>{total_partial}</td></tr>
          <tr><th>Last Recorded Mode</th><td>{last_mode.title() if last_mode!='N/A' else last_mode}</td></tr>
          <tr><th>Percentage of Full Runs</th><td>{pct_full}%</td></tr>
        </table>
      </div>
      <div style="margin-top:10px;font-size:13px;color:#666;">
        {'No verification mode history available.' if not ver_entries else ''}
      </div>
    </section>
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
          <text id="ghsVal" x="70" y="92" text-anchor="middle" font-size="28" font-family="Arial" font-weight="bold" fill="#222">{cur_ghs_val:.1f}%</text>
        </svg>
      </div>
      <div style="font-size:14px;line-height:1.5;">
  <strong>Current GHS:</strong> {cur_ghs_val:.1f}%<br>
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
  <section id="meta_learning" style="margin-top:28px">
    <h3>Meta-Learning Coefficients</h3>
    <div style="display:grid;grid-template-columns:1fr 180px;gap:24px;align-items:start;">
      <div>
        <canvas id="coefTrend" height="220"></canvas>
      </div>
      <div style="text-align:center;">
        <h4 style="margin:0 0 8px 0;font-size:14px;">Learning Stability</h4>
        <svg width="160" height="100" viewBox="0 0 160 100">
          <defs>
            <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" style="stop-color:#d73a49;stop-opacity:1" />
              <stop offset="40%" style="stop-color:#dfb317;stop-opacity:1" />
              <stop offset="80%" style="stop-color:#2cbe4e;stop-opacity:1" />
            </linearGradient>
          </defs>
          <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="url(#gaugeGrad)" stroke-width="12" stroke-linecap="round"/>
          <path d="M 20 80 A 60 60 0 0 1 140 80" fill="none" stroke="#eee" stroke-width="14" stroke-linecap="round" opacity="0.3"/>
          <line id="msiNeedle" x1="80" y1="80" x2="80" y2="30" stroke="#222" stroke-width="3" stroke-linecap="round" transform="rotate({-90 + (meta_stability_index * 1.8)} 80 80)"/>
          <circle cx="80" cy="80" r="6" fill="#222"/>
          <text x="80" y="96" text-anchor="middle" font-size="18" font-family="Arial" font-weight="bold" fill="#222">{meta_stability_index:.1f}%</text>
        </svg>
        <div style="font-size:11px;color:#666;margin-top:4px;">
          Variance: C {var_conf_msi:.4f} | D {var_drift_msi:.4f} | H {var_human_msi:.4f}
        </div>
      </div>
    </div>
    <div style="font-size:13px;color:#444;margin-top:6px;">
      Current weights — Confidence: <strong>{(coef_conf[-1] if coef_conf else 0):.3f}</strong>,
      Drift: <strong>{(coef_drift[-1] if coef_drift else 0):.3f}</strong>,
      Human Feedback: <strong>{(coef_human[-1] if coef_human else 0):.3f}</strong>
    </div>
  </section>
  <section id="predictive_insights" style="margin-top:28px">
    <h3>Predictive Adaptation Insights</h3>
    <div style="display:grid;grid-template-columns:1fr 220px;gap:24px;align-items:center;">
      <div>
        <canvas id="influenceBars" height="200"></canvas>
      </div>
      <div style="text-align:center;">
        <h4 style="margin:0 0 8px 0;font-size:14px;">Predicted Improvement</h4>
        <svg width="180" height="110" viewBox="0 0 180 110">
          <defs>
            <linearGradient id="impGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" style="stop-color:#d73a49;stop-opacity:1" />
              <stop offset="50%" style="stop-color:#dfb317;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#2cbe4e;stop-opacity:1" />
            </linearGradient>
          </defs>
          <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke="url(#impGrad)" stroke-width="12" stroke-linecap="round"/>
          <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke="#eee" stroke-width="14" stroke-linecap="round" opacity="0.3"/>
          <line id="impNeedle" x1="90" y1="90" x2="90" y2="30" stroke="#222" stroke-width="3" stroke-linecap="round" />
          <circle cx="90" cy="90" r="6" fill="#222"/>
          <text id="impText" x="90" y="104" text-anchor="middle" font-size="18" font-family="Arial" font-weight="bold" fill="#222"></text>
        </svg>
        <div style="font-size:12px;color:#666;margin-top:4px;">Confidence: <span id="planConf">{plan_conf_level}%</span></div>
      </div>
    </div>
    <div style="font-size:13px;color:#444;margin-top:6px;">
      <div><strong>Predicted ΔGHS:</strong> <span id="predDelta">{predicted_improvement:+.1f}%</span></div>
      <div><strong>Plan Coefficients:</strong> conf=<span id="pcConf">{proposed_coeffs['confidence_weight']:.3f}</span>, drift=<span id="pcDrift">{proposed_coeffs['drift_weight']:.3f}</span>, human=<span id="pcHuman">{proposed_coeffs['human_feedback_weight']:.3f}</span></div>
      <div style="font-size:12px;color:#666;">Updated: {predictive_ts or now}</div>
    </div>
  </section>
<script>
(function() {{
  // Verification Mode Timeline Chart
  const verLabels = {json.dumps(ver_labels)};
  const verModes = {json.dumps(ver_modes)};
  function drawVerModeChart(id) {{
    const c = document.getElementById(id); if(!c) return;
    const ctx = c.getContext('2d');
    const W = c.width = c.clientWidth * devicePixelRatio;
    const H = c.height = c.clientHeight * devicePixelRatio;
    ctx.scale(devicePixelRatio, devicePixelRatio);
    const pad = 32;
    const dotR = 8;
    const n = verLabels.length;
    if (n === 0) {{
      ctx.fillStyle = '#666';
      ctx.font = '15px Arial';
      ctx.fillText('No verification mode history available.', pad, H/2);
      return;
    }}
    // X positions
    const w = c.clientWidth - pad*2;
    function xv(i) {{ return pad + (i/(n-1||1))*w; }}
    // Draw axis
    ctx.strokeStyle = '#bbb'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad, H/2); ctx.lineTo(c.clientWidth-pad, H/2); ctx.stroke();
    // Draw dots
    for(let i=0;i<n;i++) {{
      const x = xv(i), y = H/2;
      ctx.beginPath();
      ctx.arc(x, y, dotR, 0, Math.PI*2);
      ctx.fillStyle = verModes[i]==='full' ? '#2cbe4e' : '#dfb317';
      ctx.fill();
      ctx.strokeStyle = '#222'; ctx.lineWidth = 1; ctx.stroke();
      // Tooltip/label
      ctx.font = '12px Arial'; ctx.fillStyle = '#222';
      ctx.textAlign = 'center';
      ctx.fillText(verLabels[i].replace('T',' ').replace('Z',''), x, y-dotR-6);
      ctx.font = '11px Arial'; ctx.fillStyle = verModes[i]==='full' ? '#2cbe4e' : '#dfb317';
      ctx.fillText(verModes[i].charAt(0).toUpperCase()+verModes[i].slice(1), x, y+dotR+13);
    }}
  }}
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
  drawVerModeChart('verModeChart');
  // Governance Pulse data
  const ghLabels = {json.dumps(gh_labels)};
  const ghValues = {json.dumps(gh_values)};
  const auditDays = {json.dumps(gh_audit_days)};
  // Coefficient trends
  const coefLabels = {json.dumps(coef_labels)};
  const coefConf = {json.dumps(coef_conf)};
  const coefDrift = {json.dumps(coef_drift)};
  const coefHuman = {json.dumps(coef_human)};
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
    // fade function (older points fade)
    const N = ghValues.length || 1; const alphaAt=(i)=> 0.35 + 0.65*(i/(N-1||1));
    // line segments with fading
    for(let i=1;i<ghValues.length;i++){{
      const x0=xv(i-1), y0=yv(ghValues[i-1]); const x1=xv(i), y1=yv(ghValues[i]);
      ctx.save(); ctx.globalAlpha = alphaAt(i); ctx.strokeStyle='#0366d6'; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.stroke(); ctx.restore();
    }}
    // points with fading + zone color
    for(let i=0;i<ghValues.length;i++){{ const x=xv(i), y=yv(ghValues[i]); ctx.save(); ctx.globalAlpha = alphaAt(i); ctx.fillStyle=zoneColor(ghValues[i]); ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2); ctx.fill(); ctx.restore(); }}
    // x labels (sparse)
    ctx.fillStyle='#222'; ctx.font='11px Arial';
    for(let i=0;i<ghLabels.length;i++){{
      const step = Math.ceil((ghLabels.length/6) || 1);
      if((i % step) === 0 || i === ghLabels.length - 1){{
        ctx.fillText(ghLabels[i], xv(i)-15, c.clientHeight-10);
      }}
    }}
  }}
  function drawAudit(id){{ const c=document.getElementById(id); if(!c) return; const ctx=c.getContext('2d'); const W=c.width=c.clientWidth*devicePixelRatio; const H=c.height=c.clientHeight*devicePixelRatio; ctx.scale(devicePixelRatio,devicePixelRatio); const pad=30; const w=c.clientWidth-pad*2; const h=c.clientHeight-pad*2; const maxY=Math.max(1,...auditDays,14); function xv(i){{ return pad + (i/(auditDays.length-1||1))*w; }} function bh(v){{ return (v/maxY)*h; }} const N=auditDays.length||1; const alphaAt=(i)=> 0.35 + 0.65*(i/(N-1||1)); ctx.strokeStyle='#999'; ctx.beginPath(); ctx.moveTo(pad,pad); ctx.lineTo(pad,c.clientHeight-pad); ctx.lineTo(c.clientWidth-pad,c.clientHeight-pad); ctx.stroke(); for(let i=0;i<auditDays.length;i++){{ const v=auditDays[i]; const x=xv(i)-6; const barH=bh(v); ctx.save(); ctx.globalAlpha = alphaAt(i); ctx.fillStyle='#888'; ctx.fillRect(x, c.clientHeight-pad-barH, 12, barH); ctx.restore(); }} ctx.fillStyle='#222'; ctx.font='11px Arial'; for(let i=0;i<auditDays.length;i++){{ if(i%Math.ceil(auditDays.length/6||1)==0 || i==auditDays.length-1){{ ctx.fillText(ghLabels[i], xv(i)-15, c.clientHeight-10); }} }} }}
  function drawCoef(id){{ const c=document.getElementById(id); if(!c) return; const ctx=c.getContext('2d'); const W=c.width=c.clientWidth*devicePixelRatio; const H=c.height=c.clientHeight*devicePixelRatio; ctx.scale(devicePixelRatio,devicePixelRatio); const pad=30; const w=c.clientWidth-pad*2; const h=c.clientHeight-pad*2; const maxY=1.0; function xv(i){{ return pad + (i/(coefLabels.length-1||1))*w; }} function yv(v){{ return c.clientHeight - pad - (v/maxY)*h; }} ctx.strokeStyle='#999'; ctx.beginPath(); ctx.moveTo(pad,pad); ctx.lineTo(pad,c.clientHeight-pad); ctx.lineTo(c.clientWidth-pad,c.clientHeight-pad); ctx.stroke(); const N=coefLabels.length||1; const alphaAt=(i)=>0.35+0.65*(i/(N-1||1)); function line(arr,color){{ for(let i=1;i<arr.length;i++){{ const x0=xv(i-1), y0=yv(arr[i-1]); const x1=xv(i), y1=yv(arr[i]); ctx.save(); ctx.globalAlpha=alphaAt(i); ctx.strokeStyle=color; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(x0,y0); ctx.lineTo(x1,y1); ctx.stroke(); ctx.restore(); }} for(let i=0;i<arr.length;i++){{ const x=xv(i), y=yv(arr[i]); ctx.save(); ctx.globalAlpha=alphaAt(i); ctx.fillStyle=color; ctx.beginPath(); ctx.arc(x,y,3,0,Math.PI*2); ctx.fill(); ctx.restore(); }} }} line(coefConf,'#0366d6'); line(coefDrift,'#f39c12'); line(coefHuman,'#8e44ad'); ctx.fillStyle='#222'; ctx.font='11px Arial'; for(let i=0;i<coefLabels.length;i++){{ const step=Math.ceil((coefLabels.length/6)||1); if((i%step)===0 || i===coefLabels.length-1){{ ctx.fillText(coefLabels[i], xv(i)-15, c.clientHeight-10); }} }} }}
  drawGhs('ghsTrend');
  drawAudit('auditCadence');
  drawCoef('coefTrend');
  // Predictive Influence Bars & Improvement Gauge
  const inflLabels = {json.dumps(influence_labels)};
  const inflValues = {json.dumps(influence_values)};
  function drawInfluenceBars(id) {{
    const c = document.getElementById(id); if(!c) return; const ctx = c.getContext('2d');
    const W = c.width = c.clientWidth * devicePixelRatio; const H = c.height = c.clientHeight * devicePixelRatio; ctx.scale(devicePixelRatio, devicePixelRatio);
    const pad = 30; const w = c.clientWidth - pad*2; const h = c.clientHeight - pad*2; const zeroY = pad + h/2;
    // axes
    ctx.strokeStyle = '#999'; ctx.beginPath(); ctx.moveTo(pad, zeroY); ctx.lineTo(c.clientWidth - pad, zeroY); ctx.stroke();
    const maxAbs = Math.max(0.01, ...inflValues.map(v=>Math.abs(v)));
    const barW = (w / Math.max(1, inflLabels.length)) * 0.6;
    for (let i=0;i<inflLabels.length;i++) {{
      const x = pad + (i+0.5)*(w/inflLabels.length) - barW/2;
      const v = inflValues[i];
      const hpix = (Math.abs(v)/maxAbs) * (h/2);
      ctx.fillStyle = v>=0 ? '#2cbe4e' : '#d73a49';
      const y = v>=0 ? (zeroY - hpix) : zeroY;
      ctx.fillRect(x, y, barW, hpix);
      ctx.fillStyle = '#222'; ctx.font = '12px Arial'; ctx.textAlign='center';
      ctx.fillText(inflLabels[i], x+barW/2, c.clientHeight - 8);
    }}
  }}
  function drawImprovementGauge() {{
    const imp = {predicted_improvement};
    const clamped = Math.max(-10, Math.min(10, imp)); // -10% .. +10%
    const angle = -90 + ((clamped + 10) / 20) * 180; // map to [-90, +90]
    const needle = document.getElementById('impNeedle');
  const t = `rotate(${{angle}} 90 90)`;
    if (needle) needle.setAttribute('transform', t);
    const txt = document.getElementById('impText');
  if (txt) txt.textContent = `${{imp.toFixed(1)}}%`;
  }}
  drawInfluenceBars('influenceBars');
  drawImprovementGauge();
  // Pulse ring color adjustment
  const ring=document.getElementById('pulseRing'); if(ring){{ const v={cur_ghs:.1f}; ring.setAttribute('stroke', zoneColor(v)); }}

  // Trust–Health Correlation panel
  function drawTrustCorrChart(id, ghs, msi) {{
    const c = document.getElementById(id);
    if (!c) return;
    const ctx = c.getContext('2d');
    ctx.clearRect(0,0,c.width,c.height);
    const w = c.width, h = c.height;
    const pad = 32, barW = 48;
    const vals = [ghs, msi];
    const labels = ['GHS', 'MSI'];
    for (let i=0;i<2;i++) {{
      let v = vals[i];
      let color = '#dfb317';
      if (v > 0.5) color = '#2cbe4e';
      else if (v < -0.5) color = '#d73a49';
      ctx.fillStyle = color;
      const x = pad + i*(w/2) + (w/4-barW/2);
      const y = h - 8;
      const barH = Math.abs(v) * (h-24);
      ctx.fillRect(x, y-barH, barW, barH);
      ctx.fillStyle = '#222'; ctx.font = '13px Arial'; ctx.textAlign='center';
      ctx.fillText(labels[i], x+barW/2, h-2);
      ctx.fillText(v.toFixed(2), x+barW/2, y-barH-6);
    }}
  }}
  drawTrustCorrChart('trustCorrChart', {trust_corr['corr_trust_GHS']:.2f}, {trust_corr['corr_trust_MSI']:.2f});
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
