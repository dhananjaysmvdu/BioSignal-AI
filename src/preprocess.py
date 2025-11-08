"""Preprocessing routines for harmonizing images and metadata inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def fit_metadata_encoders(
    df: pd.DataFrame,
    numeric_cols: Iterable[str],
    cat_cols: Iterable[str],
    *,
    save_dir: str | Path = "artifacts",
) -> Tuple[pd.DataFrame, dict[str, object]]:
    """Fit scalers/encoders for metadata and persist them to disk."""

    numeric_cols = list(numeric_cols)
    cat_cols = list(cat_cols)

    scaler = StandardScaler()
    encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")

    numeric_values = scaler.fit_transform(df[numeric_cols]) if numeric_cols else np.empty((len(df), 0))
    cat_values = encoder.fit_transform(df[cat_cols]) if cat_cols else np.empty((len(df), 0))

    transformed = np.concatenate([numeric_values, cat_values], axis=1)
    transformed_df = pd.DataFrame(transformed)

    artifact_dir = Path(save_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(scaler, artifact_dir / "numeric_scaler.joblib")
    joblib.dump(encoder, artifact_dir / "categorical_encoder.joblib")

    return transformed_df, {"scaler": scaler, "encoder": encoder}


def load_metadata_encoders(
    *, save_dir: str | Path = "artifacts"
) -> dict[str, object]:
    """Reload previously fitted metadata encoders from disk."""

    artifact_dir = Path(save_dir)
    scaler_path = artifact_dir / "numeric_scaler.joblib"
    encoder_path = artifact_dir / "categorical_encoder.joblib"

    if not scaler_path.exists() or not encoder_path.exists():
        raise FileNotFoundError(
            f"Encoder artifacts not found in {artifact_dir}. Run fit_metadata_encoders first."
        )

    scaler = joblib.load(scaler_path)
    encoder = joblib.load(encoder_path)
    return {"scaler": scaler, "encoder": encoder}


def transform_metadata(
    df: pd.DataFrame,
    encoders: dict[str, object],
    numeric_cols: Iterable[str],
    cat_cols: Iterable[str],
) -> torch.FloatTensor:
    """Apply fitted encoders and return concatenated numeric features as a tensor."""

    scaler: StandardScaler = encoders["scaler"]
    encoder: OneHotEncoder = encoders["encoder"]

    numeric_cols = list(numeric_cols)
    cat_cols = list(cat_cols)

    numeric_values = scaler.transform(df[numeric_cols]) if numeric_cols else np.empty((len(df), 0))
    cat_values = encoder.transform(df[cat_cols]) if cat_cols else np.empty((len(df), 0))

    features = np.concatenate([numeric_values, cat_values], axis=1)
    return torch.tensor(features, dtype=torch.float32)


if __name__ == "__main__":
    metadata_path = Path("data") / "sample" / "metadata.csv"
    if not metadata_path.exists():
        raise FileNotFoundError(
            "metadata.csv not found. Generate it by running src/data_loader.py first."
        )

    frame = pd.read_csv(metadata_path)
    numeric_columns = ["age"]
    categorical_columns = ["gender", "lesion_site", "label"]

    transformed_df, encoders = fit_metadata_encoders(
        frame,
        numeric_columns,
        categorical_columns,
    )

    reloaded = load_metadata_encoders()
    feature_tensor = transform_metadata(
        frame,
        reloaded,
        numeric_columns,
        categorical_columns,
    )

    print(f"Transformed DataFrame shape: {transformed_df.shape}")
    print(f"Feature tensor shape: {feature_tensor.shape}")
