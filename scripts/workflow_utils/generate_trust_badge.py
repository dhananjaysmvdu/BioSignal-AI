#!/usr/bin/env python3
"""Generate Oversight Trust Index badge and signature.

Computes trust index from:
  logs/reviewer_scores.json  (alignment per reviewer)
  logs/oversight_ledger.json (to derive disagreement rate)

Formula:
  mean_alignment = average(alignment values)
  disagreement_rate = 1 - (approvals / total_reviews)
  trust_index = mean_alignment * (1 - disagreement_rate)

Outputs:
  badges/trust_index.svg      (shield-style badge)
  badges/trust_index.sig      (sha256sum compatible line: "<hash>  trust_index.svg")
  updates README.md between TRUST_BADGE markers idempotently.
  appends / updates a line in reports/audit_summary.md with current trust index.

Exit code 0 even if inputs missing (produces 0% badge) to keep workflow resilient.
"""
from __future__ import annotations
import json, os, hashlib, datetime, re
from typing import Dict, Any, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LOGS = os.path.join(ROOT, 'logs')
REPORTS = os.path.join(ROOT, 'reports')
BADGES = os.path.join(ROOT, 'badges')
SCORES_JSON = os.path.join(LOGS, 'reviewer_scores.json')
LEDGER_JSON = os.path.join(LOGS, 'oversight_ledger.json')
SUMMARY_MD = os.path.join(REPORTS, 'audit_summary.md')
README = os.path.join(ROOT, 'README.md')

TRUST_BEGIN = '<!-- TRUST_BADGE:BEGIN -->'
TRUST_END = '<!-- TRUST_BADGE:END -->'


def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def compute_trust_index() -> Dict[str, float]:
    scores = _load_json(SCORES_JSON, {}) or {}
    ledger = _load_json(LEDGER_JSON, []) or []
    align_vals: List[float] = []
    if isinstance(scores, dict):
        for v in scores.values():
            try:
                align_vals.append(float(v.get('alignment', 0.0)))
            except Exception:
                pass
    mean_alignment = sum(align_vals)/len(align_vals) if align_vals else 0.0
    approvals = 0
    for e in ledger:
        verdict = str(e.get('verdict','')).lower()
        if verdict == 'approved':
            approvals += 1
    total_reviews = len(ledger)
    disagreement_rate = 1.0 - (approvals/total_reviews) if total_reviews else 1.0  # if none, full disagreement baseline
    trust_index = max(0.0, min(1.0, mean_alignment * (1 - disagreement_rate)))
    return {
        'mean_alignment': mean_alignment,
        'disagreement_rate': disagreement_rate,
        'trust_index': trust_index,
        'reviews': total_reviews,
        'approvals': approvals,
    }


def _color(pct: float) -> str:
    if pct >= 80:
        return '#2cbe4e'  # green
    if pct >= 60:
        return '#dfb317'  # yellow
    return '#d73a49'      # red


def generate_svg(pct: float, metrics: Dict[str, float]) -> str:
    label = 'Oversight Trust Index'
    value_text = f"{pct:.2f}%"
    color = _color(pct)
    # simple intrinsic sizing; adjust width based on chars
    label_w = 7 * len(label) + 20
    value_w = 7 * len(value_text) + 20
    total_w = label_w + value_w
    ts = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20" role="img" aria-label="{label}: {value_text}">
  <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <rect rx="3" width="{total_w}" height="20" fill="#555"/>
  <rect rx="3" x="{label_w}" width="{value_w}" height="20" fill="{color}"/>
  <rect rx="3" width="{total_w}" height="20" fill="url(#s)"/>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{label_w/2}" y="14">{label}</text>
    <text x="{label_w + value_w/2}" y="14">{value_text}</text>
  </g>
  <title>{label}: {value_text} (mean_alignment={metrics['mean_alignment']:.3f}, disagreement={metrics['disagreement_rate']:.3f}; generated {ts})</title>
</svg>'''


def write_badge(svg: str) -> str:
    os.makedirs(BADGES, exist_ok=True)
    svg_path = os.path.join(BADGES, 'trust_index.svg')
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write(svg)
    h = hashlib.sha256(svg.encode('utf-8')).hexdigest()
    sig_path = os.path.join(BADGES, 'trust_index.sig')
    with open(sig_path, 'w', encoding='utf-8') as f:
        f.write(f"{h}  trust_index.svg\n")
    return h


def update_readme():
    if not os.path.exists(README):
        return
    with open(README, 'r', encoding='utf-8') as f:
        text = f.read()
    block = f"{TRUST_BEGIN}\n![Oversight Trust Index](badges/trust_index.svg)\n{TRUST_END}"
    if TRUST_BEGIN in text:
        # replace existing block
        text = re.sub(rf'{re.escape(TRUST_BEGIN)}.*?{re.escape(TRUST_END)}', block, text, flags=re.DOTALL)
    else:
        # insert after coverage badge block if present else append
        anchor = '<!-- COVERAGE_BADGE:END -->'
        if anchor in text:
            text = text.replace(anchor, anchor + '\n\n' + block)
        else:
            text += '\n\n' + block + '\n'
    with open(README, 'w', encoding='utf-8') as f:
        f.write(text)


def update_audit_summary(pct: float):
    os.makedirs(os.path.dirname(SUMMARY_MD), exist_ok=True)
    line = f"Oversight Trust Index Badge: {pct:.2f}% (badges/trust_index.svg)"
    existing = ''
    if os.path.exists(SUMMARY_MD):
        with open(SUMMARY_MD, 'r', encoding='utf-8') as f:
            existing = f.read()
    marker = 'Oversight Trust Index Badge:'
    if marker in existing:
        # replace line
        new_lines = []
        for l in existing.splitlines():
            if l.startswith(marker):
                new_lines.append(line)
            else:
                new_lines.append(l)
        updated = '\n'.join(new_lines) + '\n'
    else:
        updated = existing.rstrip() + '\n\n' + line + '\n'
    with open(SUMMARY_MD, 'w', encoding='utf-8') as f:
        f.write(updated)


def main() -> int:
    metrics = compute_trust_index()
    pct = metrics['trust_index'] * 100.0
    svg = generate_svg(pct, metrics)
    h = write_badge(svg)
    update_readme()
    update_audit_summary(pct)
    print(json.dumps({
        'mean_alignment': metrics['mean_alignment'],
        'disagreement_rate': metrics['disagreement_rate'],
        'trust_index_pct': pct,
        'sha256': h,
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
