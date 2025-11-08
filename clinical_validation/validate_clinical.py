"""
Clinical validation runner for BioSignal-X.

Usage:
  python -m clinical_validation.validate_clinical \
    --csv path/to/external_metadata.csv \
    --model checkpoints/model_epoch1.pt \
    --out results/clinical_outputs \
    --mc-samples 20

CSV schema (columns): patient_id,image_path,age,sex,skin_type,diagnosis,site (optional)
Output: per-case JSON files and summary CSVs by site and demographics.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import torch

from src.models.biosignal_model import BioSignalModel
from src.preprocess import load_metadata_encoders, transform_metadata, fit_metadata_encoders


@dataclass
class CaseResult:
    patient_id: str
    image_path: str
    prediction: int
    confidence: float
    uncertainty: float
    explanation_link: str


def ece_score(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.digitize(probs, bins) - 1
    ece = 0.0
    for b in range(n_bins):
        mask = idx == b
        if not np.any(mask):
            continue
        acc = (labels[mask] == (probs[mask] >= 0.5)).mean()
        conf = probs[mask].mean()
        ece += (np.sum(mask) / len(probs)) * abs(acc - conf)
    return float(ece)


def enable_mc_dropout(module: torch.nn.Module) -> None:
    for m in module.modules():
        if isinstance(m, torch.nn.Dropout):
            m.train()


def prepare_metadata(df: pd.DataFrame, encoders: Dict[str, object]) -> torch.FloatTensor:
    scaler = encoders.get("scaler")
    encoder = encoders.get("encoder")
    numeric_cols = list(getattr(scaler, "feature_names_in_", ["age"]))
    cat_cols = list(getattr(encoder, "feature_names_in_", ["sex", "skin_type"]))
    # normalize columns
    work = df.copy()
    for col in numeric_cols:
        work[col] = pd.to_numeric(work.get(col, 0), errors="coerce").fillna(0)
    for col in cat_cols:
        work[col] = work.get(col, "unknown").fillna("unknown").astype(str)
    # ensure order
    work = work[numeric_cols + cat_cols]
    return transform_metadata(work, encoders, numeric_cols, cat_cols)


def load_or_fit_encoders(df: pd.DataFrame) -> Dict[str, object]:
    try:
        return load_metadata_encoders()
    except FileNotFoundError:
        _, enc = fit_metadata_encoders(
            df.rename(columns={"sex": "gender"}),
            numeric_cols=["age"],
            cat_cols=["gender", "skin_type"],
        )
        return enc


def run_inference(args: argparse.Namespace) -> None:
    csv_path = Path(args.csv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = out_dir / "explanations"; plots_dir.mkdir(exist_ok=True)

    df = pd.read_csv(csv_path)
    # Basic sanity
    required = ["patient_id", "image_path", "age", "sex", "diagnosis"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    encoders = load_or_fit_encoders(df)
    metadata_tensor = prepare_metadata(df, encoders)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = BioSignalModel(metadata_dim=metadata_tensor.shape[1]).to(device)
    if args.model:
        ckpt = torch.load(args.model, map_location=device)
        state = ckpt.get("model_state", ckpt)
        model.load_state_dict(state, strict=False)

    # Image preprocessing
    from PIL import Image
    from torchvision import transforms
    tfm = transforms.Compose([
        transforms.Resize((224,224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])
    ])

    # MC Dropout
    T = int(args.mc_samples)
    enable_mc_dropout(model)

    results: List[CaseResult] = []
    y_true, y_prob = [], []

    # Optional MLflow logging
    mlflow_active = False
    if getattr(args, "mlflow", False):
        try:
            from src.logging_utils.mlflow_logger import init_mlflow, log_metrics as mlflow_log_metrics, log_artifacts as mlflow_log_artifacts, end_run as mlflow_end_run
            mlflow_active = init_mlflow(
                run_name=f"clinical-validate-{Path(args.csv).stem}-{pd.Timestamp.utcnow().strftime('%Y%m%d-%H%M%S')}",
                params={
                    "mc_samples": int(args.mc_samples),
                    "num_cases": int(len(df)),
                    "model": str(args.model) if args.model else "random-init",
                },
            )
        except Exception:
            mlflow_active = False

    for idx, row in df.iterrows():
        img_path = Path(row["image_path"]) if Path(row["image_path"]).is_absolute() else csv_path.parent / row["image_path"]
        image = Image.open(img_path).convert("RGB")
        x = tfm(image).unsqueeze(0).to(device)
        m = metadata_tensor[idx:idx+1].to(device)
        probs_T = []
        with torch.no_grad():
            for _ in range(T):
                logits, p = model(x, m)
                probs_T.append(p[:,1].detach().cpu().numpy())
        P = np.stack(probs_T, axis=0)
        P_mean = P.mean(axis=0)[0].item()
        P_var = P.var(axis=0)[0].item()
        pred = int(P_mean >= 0.5)
        conf = float(P_mean)
        # Save placeholder explanation link (to be generated by explainer pipeline)
        expl_link = str((plots_dir / f"{row['patient_id']}").as_posix())
        results.append(CaseResult(
            patient_id=str(row["patient_id"]),
            image_path=str(img_path),
            prediction=pred,
            confidence=conf,
            uncertainty=float(P_var),
            explanation_link=expl_link
        ))
        if "diagnosis" in df.columns:
            y_true.append(1 if str(row["diagnosis"]).lower() in {"melanoma","malignant","cancer"} else 0)
            y_prob.append(P_mean)

    # Persist per-case JSON
    for r in results:
        with open(out_dir / f"case_{r.patient_id}.json", 'w', encoding='utf-8') as fh:
            json.dump(asdict(r), fh, indent=2)

    # Summaries
    if y_true:
        import csv as _csv
        from sklearn.metrics import roc_auc_score, confusion_matrix, brier_score_loss
        y_true_np = np.array(y_true); y_prob_np = np.array(y_prob)
        try:
            auc = roc_auc_score(y_true_np, y_prob_np)
        except Exception:
            auc = float('nan')
        y_pred = (y_prob_np >= 0.5).astype(int)
        if len(set(y_true_np))>1:
            tn, fp, fn, tp = confusion_matrix(y_true_np, y_pred).ravel()
            sens = tp/(tp+fn+1e-8); spec = tn/(tn+fp+1e-8)
        else:
            sens = float('nan'); spec = float('nan')
        brier = brier_score_loss(y_true_np, y_prob_np)
        ece = ece_score(y_prob_np, y_true_np)
        with open(out_dir / "summary.csv", 'w', newline='') as fh:
            w = _csv.DictWriter(fh, fieldnames=["auc","sensitivity","specificity","brier","ece"]) ; w.writeheader()
            w.writerow({"auc":auc,"sensitivity":sens,"specificity":spec,"brier":brier,"ece":ece})
        if mlflow_active:
            try:
                mlflow_log_metrics({
                    "auc": float(auc),
                    "sensitivity": float(sens),
                    "specificity": float(spec),
                    "brier": float(brier),
                    "ece": float(ece),
                })
            except Exception:
                pass

    # Per-site/per-demographic summaries if present
    group_cols = [c for c in ["site","sex","skin_type","age"] if c in df.columns]
    if group_cols and y_true:
        metrics = []
        for col in group_cols:
            for level, sub in df.groupby(col):
                idxs = sub.index.tolist()
                yp = np.array([y_prob[i] for i in idxs if i < len(y_prob)])
                yt = np.array([y_true[i] for i in idxs if i < len(y_true)])
                if len(yt) < 3:
                    continue
                try:
                    from sklearn.metrics import roc_auc_score, confusion_matrix
                    auc = roc_auc_score(yt, yp)
                except Exception:
                    auc = float('nan')
                yhat = (yp>=0.5).astype(int)
                if len(set(yt))>1:
                    tn, fp, fn, tp = confusion_matrix(yt, yhat).ravel()
                    sens = tp/(tp+fn+1e-8); spec = tn/(tn+fp+1e-8)
                else:
                    sens=float('nan'); spec=float('nan')
                metrics.append({"group": f"{col}:{level}", "auc": float(auc), "sens": float(sens), "spec": float(spec)})
    pd.DataFrame(metrics).to_csv(out_dir/"group_summary.csv", index=False)

    # Traceability log
    trace_dir = Path("logs"); trace_dir.mkdir(exist_ok=True)
    trace_file = trace_dir / "traceability.json"
    record = {
        "event": "clinical_validate",
        "model_checkpoint": str(args.model),
        "csv": str(csv_path),
        "outputs": str(out_dir),
    }
    try:
        if trace_file.exists():
            existing = json.loads(trace_file.read_text(encoding='utf-8'))
            if isinstance(existing, list):
                existing.append(record)
            else:
                existing = [existing, record]
        else:
            existing = [record]
        trace_file.write_text(json.dumps(existing, indent=2), encoding='utf-8')
    except Exception:
        pass

    # Log artifacts and end MLflow run
    if mlflow_active:
        try:
            mlflow_log_artifacts([out_dir])
            mlflow_end_run()
        except Exception:
            pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--model", type=Path, default=None)
    p.add_argument("--out", type=Path, default=Path("results/clinical_outputs"))
    p.add_argument("--mc-samples", type=int, default=20)
    p.add_argument("--mlflow", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    run_inference(parse_args())
