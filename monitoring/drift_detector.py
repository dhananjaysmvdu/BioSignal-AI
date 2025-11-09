"""Simple data drift detector comparing reference vs current cohort distributions.

Computes Jensen-Shannon divergence (JSD) for numeric and categorical variables.
Outputs a JSON report with per-feature drift scores and flags.

Usage:
  python -m monitoring.drift_detector --ref path/to/ref.csv --cur path/to/current.csv --out logs/drift_report.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd


def jsd(p: np.ndarray, q: np.ndarray) -> float:
    p = p.astype(float)
    q = q.astype(float)
    p = p / (p.sum() + 1e-12)
    q = q / (q.sum() + 1e-12)
    m = 0.5 * (p + q)
    def _kl(a, b):
        a = np.clip(a, 1e-12, 1)
        b = np.clip(b, 1e-12, 1)
        return float(np.sum(a * np.log(a / b)))
    return 0.5 * (_kl(p, m) + _kl(q, m))


def cat_distribution(s: pd.Series) -> Tuple[np.ndarray, Dict[str, int]]:
    vals, counts = np.unique(s.astype(str).fillna("unknown").to_numpy(), return_counts=True)
    mapping = {v: i for i, v in enumerate(vals)}
    dist = np.zeros(len(vals), dtype=float)
    for v, c in zip(vals, counts):
        dist[mapping[v]] = c
    return dist, mapping


def cat_jsd(a: pd.Series, b: pd.Series) -> float:
    da, ma = cat_distribution(a)
    db, mb = cat_distribution(b)
    # align supports
    all_keys = sorted(set(ma.keys()) | set(mb.keys()))
    va = np.array([da[ma[k]] if k in ma else 0.0 for k in all_keys], dtype=float)
    vb = np.array([db[mb[k]] if k in mb else 0.0 for k in all_keys], dtype=float)
    return jsd(va, vb)


def num_jsd(a: pd.Series, b: pd.Series, bins: int = 20) -> float:
    aa = pd.to_numeric(a, errors="coerce").dropna().to_numpy()
    bb = pd.to_numeric(b, errors="coerce").dropna().to_numpy()
    if len(aa) < 3 or len(bb) < 3:
        return float("nan")
    min_v = float(min(aa.min(), bb.min()))
    max_v = float(max(aa.max(), bb.max()))
    if max_v <= min_v:
        return 0.0
    hist_a, _ = np.histogram(aa, bins=bins, range=(min_v, max_v))
    hist_b, _ = np.histogram(bb, bins=bins, range=(min_v, max_v))
    return jsd(hist_a, hist_b)


def detect_drift(ref_csv: Path, cur_csv: Path, threshold: float = 0.1) -> Dict[str, object]:
    # Graceful handling for missing or empty CSVs
    if (not ref_csv.exists()) or (not cur_csv.exists()) or ref_csv.stat().st_size == 0 or cur_csv.stat().st_size == 0:
        report: Dict[str, object] = {
            "reference": str(ref_csv),
            "current": str(cur_csv),
            "threshold": threshold,
            "features": {},
            "feature_drifts": {},
            "overall_drift_rate": 0.0,
            "timestamp": pd.Timestamp.utcnow().isoformat() + "Z",
        }
        return report

    ref = pd.read_csv(ref_csv)
    cur = pd.read_csv(cur_csv)
    report: Dict[str, object] = {
        "reference": str(ref_csv),
        "current": str(cur_csv),
        "threshold": threshold,
        "features": {},
    }
    # Identify columns
    candidate_num = [c for c in ref.columns if pd.api.types.is_numeric_dtype(ref[c])]
    candidate_cat = [c for c in ref.columns if c not in candidate_num]
    # Common columns only
    candidate_num = [c for c in candidate_num if c in cur.columns]
    candidate_cat = [c for c in candidate_cat if c in cur.columns]

    features = {}
    # Numeric
    for c in candidate_num:
        score = num_jsd(ref[c], cur[c])
        features[c] = {"type": "numeric", "jsd": score, "drift": bool(score > threshold if not np.isnan(score) else False)}
    # Categorical
    for c in candidate_cat:
        score = cat_jsd(ref[c], cur[c])
        features[c] = {"type": "categorical", "jsd": score, "drift": bool(score > threshold if not np.isnan(score) else False)}

    report["features"] = features
    # Back-compat + explicit alias expected by some consumers
    report["feature_drifts"] = features
    # Overall drift proportion
    valid = [v for v in features.values() if not np.isnan(v["jsd"]) if isinstance(v["jsd"], float)]
    rate = float(np.mean([1.0 if v["drift"] else 0.0 for v in valid])) if valid else 0.0
    report["overall_drift_rate"] = rate
    report["timestamp"] = pd.Timestamp.utcnow().isoformat() + "Z"
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", type=Path, required=True, help="Reference CSV (baseline)")
    ap.add_argument("--cur", type=Path, required=True, help="Current CSV (monitoring cohort)")
    ap.add_argument("--out", type=Path, default=Path("logs/drift_report.json"))
    ap.add_argument("--threshold", type=float, default=0.1)
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = detect_drift(args.ref, args.cur, threshold=args.threshold)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote drift report to {args.out}")


if __name__ == "__main__":
    main()
