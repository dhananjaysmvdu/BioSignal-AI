"""Optional MLflow logging utilities for BioSignal-X.

Gracefully no-op if mlflow is not installed or MLFLOW_TRACKING_URI not set.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable

try:
    import mlflow  # type: ignore
except Exception:  # pragma: no cover
    mlflow = None  # type: ignore

_ACTIVE = {"run": None}


def init_mlflow(run_name: str, params: Dict[str, object] | None = None) -> bool:
    if mlflow is None:
        return False
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        return False
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT", "BioSignalX"))
    run = mlflow.start_run(run_name=run_name)
    _ACTIVE["run"] = run
    if params:
        mlflow.log_params(params)
    return True


def log_metrics(metrics: Dict[str, float], step: int | None = None) -> None:
    if mlflow is None or _ACTIVE["run"] is None:
        return
    mlflow.log_metrics(metrics, step=step)


def log_artifacts(paths: Iterable[str | Path]) -> None:
    if mlflow is None or _ACTIVE["run"] is None:
        return
    for p in paths:
        p = Path(p)
        if p.is_dir():
            mlflow.log_artifacts(str(p))
        elif p.exists():
            mlflow.log_artifact(str(p))


def end_run():  # pragma: no cover
    if mlflow is None or _ACTIVE["run"] is None:
        return
    mlflow.end_run()
    _ACTIVE["run"] = None
