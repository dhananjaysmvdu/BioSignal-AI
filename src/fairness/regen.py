"""Fairness regeneration utilities.
Generates per-attribute fairness JSON files and a consolidated summary.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

def _safe_auc(y_true, y_prob) -> float:
    try:
        return float(roc_auc_score(y_true, y_prob))
    except Exception:
        return float('nan')

def _ece(y_true, y_prob, n_bins: int = 10) -> float:
    bins = np.linspace(0,1,n_bins+1)
    idx = np.digitize(y_prob, bins) - 1
    ece = 0.0
    total = len(y_true)
    for b in range(n_bins):
        m = idx == b
        if not np.any(m):
            continue
        conf = float(np.mean(y_prob[m]))
        acc = float(np.mean((y_prob[m] >= 0.5) == y_true[m]))
        ece += abs(acc - conf) * (np.sum(m)/total)
    return float(ece)

def regenerate_fairness(predictions_csv: Path,
                        output_dir: Path,
                        attributes: Optional[Iterable[str]] = None,
                        summary_filename: str = 'fairness_summary.json') -> Dict[str, Any]:
    """Regenerate fairness JSONs and consolidated summary.

    Parameters
    ----------
    predictions_csv : Path
        CSV containing at least columns y_true, y_prob and demographic attributes.
    output_dir : Path
        Directory to write per-attribute fairness JSON and summary.
    attributes : Iterable[str], optional
        Specific attributes to evaluate; if None, infer low-cardinality object columns.
    summary_filename : str
        Name for consolidated summary file.

    Returns
    -------
    Dict[str, Any]
        Summary dict with aggregates and status fields.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / summary_filename

    if not predictions_csv.exists():
        summary = {'status': 'missing_predictions', 'aggregates': [], 'delta_auc': None, 'delta_ece': None}
        summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        return summary

    df = pd.read_csv(predictions_csv)
    if 'y_true' not in df.columns or 'y_prob' not in df.columns:
        summary = {'status': 'missing_columns', 'aggregates': [], 'delta_auc': None, 'delta_ece': None}
        summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        return summary

    y_true = df['y_true'].values
    y_prob = df['y_prob'].values

    if attributes is None:
        # infer attributes: object/string columns with <= 8 unique levels
        cand = []
        for c in df.columns:
            if c in {'y_true','y_prob'}:
                continue
            if df[c].dtype == 'object' and df[c].nunique() <= 8:
                cand.append(c)
        attributes = cand

    aggregates: List[Dict[str, Any]] = []

    for attr in attributes:
        try:
            levels: Dict[str, Dict[str, float]] = {}
            for lvl, sub in df.groupby(attr):
                yt = sub['y_true'].values
                yp = sub['y_prob'].values
                levels[str(lvl)] = {
                    'auc': _safe_auc(yt, yp),
                    'ece': _ece(yt, yp)
                }
            obj = {'attribute': attr, 'levels': levels}
            out_fp = output_dir / f'{attr}_fairness.json'
            out_fp.write_text(json.dumps(obj, indent=2), encoding='utf-8')
            # compute deltas
            auc_vals = [m['auc'] for m in levels.values() if not np.isnan(m['auc'])]
            ece_vals = [m['ece'] for m in levels.values() if not np.isnan(m['ece'])]
            delta_auc = (max(auc_vals) - min(auc_vals)) if len(auc_vals) >= 2 else float('nan')
            delta_ece = (max(ece_vals) - min(ece_vals)) if len(ece_vals) >= 2 else float('nan')
            aggregates.append({'attribute': attr, 'delta_auc': delta_auc, 'delta_ece': delta_ece})
        except Exception as e:
            aggregates.append({'attribute': attr, 'error': str(e), 'delta_auc': float('nan'), 'delta_ece': float('nan')})

    # global deltas (max across attributes)
    global_delta_auc = max([a['delta_auc'] for a in aggregates if not np.isnan(a['delta_auc'])], default=None)
    global_delta_ece = max([a['delta_ece'] for a in aggregates if not np.isnan(a['delta_ece'])], default=None)

    summary = {
        'status': 'ok',
        'aggregates': aggregates,
        'delta_auc': global_delta_auc,
        'delta_ece': global_delta_ece
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary

__all__ = ['regenerate_fairness']
