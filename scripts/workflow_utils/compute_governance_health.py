#!/usr/bin/env python3
"""Compute composite Governance Health Score (GHS) and publish badge.

Inputs:
  - results/benchmark_metrics.csv (parse mean AUC)
  - results/calibration_report.csv (parse mean ECE)
  - badges/trust_index.svg (extract trust %)
  - reports/provenance_forecast.json (extract drift probability %)

Outputs:
  - reports/governance_health.json
  - badges/governance_health.svg
  - badges/governance_health.sig (sha256 compatible)
  - Update reports/audit_summary.md block GOVERNANCE_HEALTH
  - Update README.md HEALTH_BADGE block idempotently

GHS = 0.35*tech + 0.25*calib + 0.25*trust + 0.15*stability (all 0-100)
"""
from __future__ import annotations
import os, csv, json, re, hashlib, datetime
from typing import Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RESULTS = os.path.join(ROOT, 'results')
REPORTS = os.path.join(ROOT, 'reports')
BADGES = os.path.join(ROOT, 'badges')
README = os.path.join(ROOT, 'README.md')

BENCH_CSV = os.path.join(RESULTS, 'benchmark_metrics.csv')
CALIB_CSV = os.path.join(RESULTS, 'calibration_report.csv')
TRUST_SVG = os.path.join(BADGES, 'trust_index.svg')
FORECAST_JSON = os.path.join(REPORTS, 'provenance_forecast.json')
OUT_JSON = os.path.join(REPORTS, 'governance_health.json')
SUMMARY_MD = os.path.join(REPORTS, 'audit_summary.md')

GH_BEGIN = '<!-- GOVERNANCE_HEALTH:BEGIN -->'
GH_END = '<!-- GOVERNANCE_HEALTH:END -->'
HB_BEGIN = '<!-- HEALTH_BADGE:BEGIN -->'
HB_END = '<!-- HEALTH_BADGE:END -->'


def _read_mean_auc(path: str) -> float:
    if not os.path.exists(path):
        return 0.0
    auc_vals = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                for k,v in row.items():
                    if 'auc' in k.lower():
                        try:
                            auc_vals.append(float(v))
                        except Exception:
                            pass
        if auc_vals:
            return sum(auc_vals)/len(auc_vals)
    except Exception:
        pass
    return 0.0


def _read_mean_ece(path: str) -> float:
    if not os.path.exists(path):
        return 1.0
    ece_vals = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                for k,v in row.items():
                    if 'ece' in k.lower():
                        try:
                            ece_vals.append(float(v))
                        except Exception:
                            pass
        if ece_vals:
            return sum(ece_vals)/len(ece_vals)
    except Exception:
        pass
    return 1.0


def _extract_trust_pct(path: str) -> float:
    if not os.path.exists(path):
        return 0.0
    try:
        with open(path, 'r', encoding='utf-8') as f:
            s = f.read()
        m = re.search(r'(\d+(?:\.\d+)?)%', s)
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0


def _read_drift_pct(path: str) -> float:
    if not os.path.exists(path):
        return 100.0
    try:
        with open(path, 'r', encoding='utf-8') as f:
            j = json.load(f)
        # expected key used by forecast_provenance_risk.py
        v = j.get('predicted_drift_probability_pct')
        return float(v) if v is not None else 100.0
    except Exception:
        return 100.0


def _color(pct: float) -> str:
    if pct >= 80:
        return '#2cbe4e'
    if pct >= 60:
        return '#dfb317'
    return '#d73a49'


def _badge_svg(pct: float) -> str:
    color = _color(pct)
    text = f"Governance Health: {pct:.1f}%"
    ts = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    # circular badge 120x120
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120" role="img" aria-label="{text}">
  <circle cx="60" cy="60" r="54" fill="#fff" stroke="{color}" stroke-width="8" />
  <text x="60" y="54" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="10" fill="#333">Governance Health</text>
  <text x="60" y="80" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="20" fill="{color}">{pct:.0f}%</text>
  <title>{text} — generated {ts}</title>
</svg>'''


def _write_badge(svg: str) -> str:
    os.makedirs(BADGES, exist_ok=True)
    svg_path = os.path.join(BADGES, 'governance_health.svg')
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg)
    h = hashlib.sha256(svg.encode('utf-8')).hexdigest()
    with open(os.path.join(BADGES, 'governance_health.sig'), 'w', encoding='utf-8') as f:
        f.write(f"{h}  governance_health.svg\n")
    return h


def _update_summary(ghs: float, tech: float, calib: float, trust: float, stab: float) -> None:
    os.makedirs(REPORTS, exist_ok=True)
    existing = ''
    if os.path.exists(SUMMARY_MD):
        with open(SUMMARY_MD, 'r', encoding='utf-8') as f:
            existing = f.read()
    block = (
        f"{GH_BEGIN}\n"
        f"Governance Health Score: {ghs:.1f}%\n"
        f"Technical: {tech:.1f} | Calibration: {calib:.1f} | Ethical: {trust:.1f} | Stability: {stab:.1f}\n"
        f"Updated: {datetime.datetime.utcnow().replace(microsecond=0).isoformat()}Z\n"
        f"{GH_END}"
    )
    if GH_BEGIN in existing:
        new = re.sub(rf'{re.escape(GH_BEGIN)}.*?{re.escape(GH_END)}', block, existing, flags=re.DOTALL)
    else:
        new = existing.rstrip() + ('\n\n' if existing.strip() else '') + block + '\n'
    with open(SUMMARY_MD, 'w', encoding='utf-8') as f:
        f.write(new)


def _update_readme_badge() -> None:
    if not os.path.exists(README):
        return
    with open(README, 'r', encoding='utf-8') as f:
        text = f.read()
    block = f"{HB_BEGIN}\n![Governance Health](badges/governance_health.svg)\n{HB_END}"
    if HB_BEGIN in text:
        text = re.sub(rf'{re.escape(HB_BEGIN)}.*?{re.escape(HB_END)}', block, text, flags=re.DOTALL)
    else:
        # insert after TRUST badge block if present
        anchor = '<!-- TRUST_BADGE:END -->'
        if anchor in text:
            text = text.replace(anchor, anchor + '\n\n' + block)
        else:
            text += '\n\n' + block + '\n'
    with open(README, 'w', encoding='utf-8') as f:
        f.write(text)


def main() -> int:
    auc = _read_mean_auc(BENCH_CSV)
    ece = _read_mean_ece(CALIB_CSV)
    trust = _extract_trust_pct(TRUST_SVG)
    drift = _read_drift_pct(FORECAST_JSON)

    tech_score = max(0.0, min(100.0, auc * 100.0))
    calib_score = max(0.0, min(100.0, (1.0 - ece) * 100.0))
    trust_score = max(0.0, min(100.0, trust))
    stability_score = max(0.0, min(100.0, (1.0 - (drift/100.0)) * 100.0))

    ghs = 0.35*tech_score + 0.25*calib_score + 0.25*trust_score + 0.15*stability_score
    ghs = max(0.0, min(100.0, ghs))

    os.makedirs(REPORTS, exist_ok=True)
    payload = {
        'GovernanceHealthScore': round(ghs, 1),
        'Components': {
            'Technical': round(tech_score, 1),
            'Calibration': round(calib_score, 1),
            'EthicalTrust': round(trust_score, 1),
            'OperationalStability': round(stability_score, 1),
        },
        'Timestamp': datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
    }
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)

    svg = _badge_svg(payload['GovernanceHealthScore'])
    _write_badge(svg)
    _update_summary(payload['GovernanceHealthScore'], payload['Components']['Technical'], payload['Components']['Calibration'], payload['Components']['EthicalTrust'], payload['Components']['OperationalStability'])
    _update_readme_badge()

    # Print concise summary for CI logs
    print(json.dumps(payload))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
