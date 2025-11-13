#!/usr/bin/env python3
"""
Governance Reflex Meta-Performance Evaluator
===========================================
Assess drift and meta-performance of the Governance Reflex Learning Model (GRLM).

Computations:
- ΔR² between last two model training runs (or 0 if insufficient history)
- Prediction Error Drift using MAE difference (normalized)
- Meta-Performance Index (MPI) = 100 × (1 − normalized_error_drift) × (1 + ΔR²/2)

Classification:
  MPI ≥ 80      -> Stable learning
  60 ≤ MPI < 80 -> Mild drift
  MPI < 60      -> Learning degradation

Outputs:
- reflex_meta_performance.json
- Updates audit summary block REFLEX_META

Always exits 0; graceful on insufficient data.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, UTC
from typing import Any, Dict, List


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def compute_delta_r2(history: List[Dict[str, Any]]) -> float:
    if not history or len(history) < 2:
        return 0.0
    last = history[-1].get("r2", 0.0)
    prev = history[-2].get("r2", 0.0)
    return last - prev


def compute_error_drift(history: List[Dict[str, Any]]) -> float:
    if not history or len(history) < 2:
        return 0.0
    last_mae = history[-1].get("mae", 0.0)
    prev_mae = history[-2].get("mae", 0.0)
    drift = last_mae - prev_mae
    return drift


def normalize_error_drift(drift: float, prev_mae: float) -> float:
    if prev_mae <= 0:
        return 0.0 if drift <= 0 else 1.0
    # scale absolute drift relative to previous mae
    norm = abs(drift) / prev_mae
    return max(0.0, min(1.0, norm))


def classify_mpi(mpi: float) -> str:
    if mpi >= 80:
        return "Stable learning"
    if mpi >= 60:
        return "Mild drift"
    return "Learning degradation"


def update_audit_summary(audit_path: Path, mpi: float, delta_r2: float, drift: float, status: str) -> None:
    marker_begin = "<!-- REFLEX_META:BEGIN -->"
    marker_end = "<!-- REFLEX_META:END -->"
    block = f"{marker_begin}\nReflex Meta-Performance: MPI={mpi:.2f}%, ΔR²={delta_r2:+.3f}, drift={drift:+.3f} → {status}.\n{marker_end}\n"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    if audit_path.exists():
        content = audit_path.read_text(encoding='utf-8')
        pattern = re.compile(r"<!-- REFLEX_META:BEGIN -->.*?<!-- REFLEX_META:END -->\n?", re.DOTALL)
        if pattern.search(content):
            content = pattern.sub(block, content)
        else:
            content += f"\n{block}"
        tmp = audit_path.with_suffix('.tmp')
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(audit_path)
    else:
        audit_path.write_text(block, encoding='utf-8')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate reflex learning meta-performance and drift")
    parser.add_argument("--history", type=Path, default=Path("logs/reflex_model_history.json"), help="Path to reflex model history JSON")
    parser.add_argument("--learning-model", type=Path, default=Path("reports/reflex_learning_model.json"), help="Path to latest learning model JSON")
    parser.add_argument("--reflex", type=Path, default=Path("reports/reflex_evaluation.json"), help="Path to reflex evaluation JSON")
    parser.add_argument("--output", type=Path, default=Path("reports/reflex_meta_performance.json"), help="Path to output meta performance JSON")
    parser.add_argument("--audit-summary", type=Path, default=Path("reports/audit_summary.md"), help="Path to audit summary markdown")
    args = parser.parse_args(argv)

    history = load_json(args.history)
    if not isinstance(history, list):
        history = []
    learning_model = load_json(args.learning_model) or {}
    reflex_eval = load_json(args.reflex) or {}

    delta_r2 = compute_delta_r2(history)
    error_drift = compute_error_drift(history)
    prev_mae = history[-2].get("mae", 0.0) if len(history) >= 2 else 0.0
    norm_drift = normalize_error_drift(error_drift, prev_mae)

    # MPI formula
    mpi = 100.0 * (1 - norm_drift) * (1 + (delta_r2 / 2.0))
    # Guard against negative scaling
    if mpi < 0:
        mpi = 0.0

    status = classify_mpi(mpi)

    meta_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mpi": round(mpi, 4),
        "delta_r2": round(delta_r2, 4),
        "error_drift": round(error_drift, 4),
        "normalized_error_drift": round(norm_drift, 4),
        "classification": status,
        "latest_r2": learning_model.get("r2", 0.0),
        "latest_mae": learning_model.get("mae", 0.0),
        "previous_r2": history[-2].get("r2", 0.0) if len(history) >= 2 else None,
        "previous_mae": prev_mae if len(history) >= 2 else None,
        "history_length": len(history)
    }

    # Save output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_suffix('.tmp')
    tmp.write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(args.output)

    # Update audit summary
    update_audit_summary(args.audit_summary, mpi, delta_r2, error_drift, status)

    print(json.dumps({"status": "ok", "classification": status, "mpi": mpi, "delta_r2": delta_r2}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
