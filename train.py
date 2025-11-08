"""Training script for multimodal BioSignal-AI experiments."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Dict, Iterable, Tuple

import pandas as pd
import numpy as np
import torch
from torch.optim import Adam
from torch.optim.lr_scheduler import StepLR
from torch.utils.data import DataLoader, Subset
from tqdm.auto import tqdm

from src.data_loader import SkinDataset, create_sample_dataset, stratified_split_by_site
from src.models.biosignal_model import BioSignalModel
from src.preprocess import load_metadata_encoders, transform_metadata
from sklearn.metrics import brier_score_loss, roc_auc_score, confusion_matrix
from datetime import datetime
import hashlib
import json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train BioSignal-AI multimodal model")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=4, help="Mini-batch size")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate for Adam")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the latest checkpoint in the checkpoints directory",
    )
    parser.add_argument("--site-split", action="store_true", help="Use site-aware stratified split if site column present")
    parser.add_argument("--mlflow", action="store_true", help="Enable MLflow logging if configured")
    return parser.parse_args()


def ensure_sample_data(metadata_path: Path) -> None:
    if metadata_path.exists():
        return
    target_dir = metadata_path.parent
    print(f"metadata.csv not found at {metadata_path}. Generating synthetic dataset...")
    create_sample_dataset(target_dir, n=64)


def load_encoders(metadata_path: Path) -> Tuple[Dict[str, object], Iterable[str], Iterable[str]]:
    try:
        encoders = load_metadata_encoders()
    except FileNotFoundError:
        from src.preprocess import fit_metadata_encoders

        print("Encoder artifacts missing. Fitting new encoders from metadata.csv ...")
        frame = pd.read_csv(metadata_path)
        numeric_cols = ["age"]
        cat_cols = ["gender", "lesion_site"]
        _, encoders = fit_metadata_encoders(
            frame,
            numeric_cols,
            cat_cols,
        )
    scaler = encoders.get("scaler")
    encoder = encoders.get("encoder")

    numeric_cols = list(getattr(scaler, "feature_names_in_", ["age"]))
    cat_cols = list(getattr(encoder, "feature_names_in_", ["gender", "lesion_site"]))
    return encoders, numeric_cols, cat_cols


def prepare_dataloaders(
    dataset: SkinDataset,
    batch_size: int,
    *,
    site_split: bool = False,
) -> Tuple[DataLoader, DataLoader]:
    num_samples = len(dataset)
    if num_samples < 2:
        raise ValueError("Dataset must contain at least two samples for train/val split")

    if site_split and hasattr(dataset, "frame"):
        # Use site-aware split if possible; fallback handled inside helper
        train_indices, val_indices = stratified_split_by_site(dataset.frame, test_ratio=0.2)
    else:
        indices = torch.randperm(num_samples).tolist()
        split = math.ceil(0.8 * num_samples)
        train_indices = indices[:split]
        val_indices = indices[split:]

    if not val_indices:
        val_indices = train_indices[-1:]
        train_indices = train_indices[:-1]

    train_subset = Subset(dataset, train_indices)
    val_subset = Subset(dataset, val_indices)

    train_loader = DataLoader(
        train_subset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
    )

    val_loader = DataLoader(
        val_subset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
    )

    return train_loader, val_loader


def find_latest_checkpoint(checkpoint_dir: Path) -> Path | None:
    checkpoints = sorted(checkpoint_dir.glob("model_epoch*.pt"))
    return checkpoints[-1] if checkpoints else None


def metadata_batch_to_tensor(
    raw_metadata_batch,
    encoders: Dict[str, object],
    numeric_cols: Iterable[str],
    cat_cols: Iterable[str],
) -> torch.FloatTensor:
    frame = pd.DataFrame(raw_metadata_batch)
    frame = frame.copy()

    for col in numeric_cols:
        if col not in frame.columns:
            frame[col] = 0
    for col in cat_cols:
        if col not in frame.columns:
            frame[col] = "unknown"

    frame[numeric_cols] = frame[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    frame[cat_cols] = frame[cat_cols].fillna("unknown").astype(str)

    ordered_cols = list(numeric_cols) + list(cat_cols)
    frame = frame[ordered_cols]

    return transform_metadata(frame, encoders, numeric_cols, cat_cols)


def write_metrics_row(metrics_path: Path, row: Dict[str, float]) -> None:
    file_exists = metrics_path.exists()
    with metrics_path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["epoch", "train_loss", "val_loss", "val_acc"])
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


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
    """Enable dropout layers during evaluation for MC Dropout sampling."""
    for m in module.modules():
        if isinstance(m, torch.nn.Dropout):
            m.train()


def main() -> None:
    args = parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    if device.type == "cuda":
        print(f"CUDA device: {torch.cuda.get_device_name(device)}")

    metadata_path = Path("data") / "sample" / "metadata.csv"
    ensure_sample_data(metadata_path)

    encoders, numeric_cols, cat_cols = load_encoders(metadata_path)

    dataset = SkinDataset(
        metadata_path,
        return_raw_metadata=True,
    )

    metadata_dim = transform_metadata(dataset.frame, encoders, numeric_cols, cat_cols).shape[1]

    train_loader, val_loader = prepare_dataloaders(dataset, args.batch_size, site_split=args.site_split)

    model = BioSignalModel(metadata_dim=metadata_dim)
    model.to(device)

    criterion = torch.nn.CrossEntropyLoss()
    optimizer = Adam(model.parameters(), lr=args.lr)
    scheduler = StepLR(optimizer, step_size=3, gamma=0.1)

    checkpoint_dir = Path("checkpoints")
    checkpoint_dir.mkdir(exist_ok=True)
    metrics_path = checkpoint_dir / "metrics.csv"

    # Optional MLflow logging
    mlflow_active = False
    if args.mlflow:
        try:
            from src.logging_utils.mlflow_logger import init_mlflow, log_metrics as mlflow_log_metrics, log_artifacts as mlflow_log_artifacts, end_run as mlflow_end_run, set_tags as mlflow_set_tags
            mlflow_active = init_mlflow(
                run_name=f"train-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
                params={
                    "epochs": args.epochs,
                    "batch_size": args.batch_size,
                    "lr": args.lr,
                    "resume": args.resume,
                    "device": str(device),
                    "dataset_size": len(dataset),
                },
            )
        except Exception:
            mlflow_active = False

    start_epoch = 0
    if args.resume:
        latest = find_latest_checkpoint(checkpoint_dir)
        if latest and latest.exists():
            print(f"Resuming from checkpoint: {latest}")
            checkpoint = torch.load(latest, map_location=device)
            model.load_state_dict(checkpoint["model_state"])
            optimizer.load_state_dict(checkpoint["optimizer_state"])
            scheduler.load_state_dict(checkpoint["scheduler_state"])
            start_epoch = checkpoint.get("epoch", 0)
        else:
            print("No checkpoint found. Starting from scratch.")

    for epoch in range(start_epoch, args.epochs):
        model.train()
        train_loss = 0.0
        total_train = 0

        train_iterator = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{args.epochs} [train]", leave=False)
        for batch in train_iterator:
            images, _, labels, raw_metadata = batch
            images = images.to(device)
            labels = labels.to(device)

            metadata_tensor = metadata_batch_to_tensor(
                raw_metadata,
                encoders,
                numeric_cols,
                cat_cols,
            ).to(device)

            optimizer.zero_grad()
            logits, probs = model(images, metadata_tensor)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            batch_size = images.size(0)
            train_loss += loss.item() * batch_size
            total_train += batch_size
            train_iterator.set_postfix(loss=loss.item())

        scheduler.step()
        avg_train_loss = train_loss / max(total_train, 1)

        model.eval()
        val_loss = 0.0
        correct = 0
        total_val = 0
        all_probs: list[float] = []
        all_labels: list[int] = []
        with torch.no_grad():
            val_iterator = tqdm(val_loader, desc=f"Epoch {epoch + 1}/{args.epochs} [val]", leave=False)
            for batch in val_iterator:
                images, _, labels, raw_metadata = batch
                images = images.to(device)
                labels = labels.to(device)
                metadata_tensor = metadata_batch_to_tensor(
                    raw_metadata,
                    encoders,
                    numeric_cols,
                    cat_cols,
                ).to(device)

                logits, probs = model(images, metadata_tensor)
                loss = criterion(logits, labels)

                batch_size = images.size(0)
                val_loss += loss.item() * batch_size
                total_val += batch_size
                preds = probs.argmax(dim=1)
                correct += (preds == labels).sum().item()
                all_probs.extend(probs[:, 1].detach().cpu().numpy().tolist())
                all_labels.extend(labels.detach().cpu().numpy().tolist())

        avg_val_loss = val_loss / max(total_val, 1)
        val_acc = correct / max(total_val, 1)

        print(
            f"Epoch {epoch + 1}/{args.epochs} :: train_loss={avg_train_loss:.4f} val_loss={avg_val_loss:.4f} val_acc={val_acc:.3f}"
        )

        # MLflow: log basic metrics early (will also log calibration below)
        if mlflow_active:
            try:
                mlflow_log_metrics({
                    "train_loss": float(avg_train_loss),
                    "val_loss": float(avg_val_loss),
                    "val_acc": float(val_acc),
                }, step=epoch + 1)
            except Exception:
                pass

        checkpoint_path = checkpoint_dir / f"model_epoch{epoch + 1}.pt"
        torch.save(
            {
                "epoch": epoch + 1,
                "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "scheduler_state": scheduler.state_dict(),
            },
            checkpoint_path,
        )

        write_metrics_row(
            metrics_path,
            {
                "epoch": epoch + 1,
                "train_loss": avg_train_loss,
                "val_loss": avg_val_loss,
                "val_acc": val_acc,
            },
        )

        # Calibration metrics and MC Dropout uncertainty
        calib_dir = Path("results"); calib_dir.mkdir(exist_ok=True)
        calib_path = calib_dir / "calibration_report.csv"
        y_true = np.array(all_labels)
        y_prob = np.array(all_probs)
        try:
            auc = roc_auc_score(y_true, y_prob)
        except Exception:
            auc = float("nan")
        y_pred = (y_prob >= 0.5).astype(int)
        if len(set(y_true)) > 1:
            tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
            sens = tp / (tp + fn + 1e-8)
            spec = tn / (tn + fp + 1e-8)
        else:
            sens = float("nan"); spec = float("nan")
        brier = brier_score_loss(y_true, y_prob) if len(y_prob) > 0 else float("nan")
        ece = ece_score(y_prob, y_true) if len(y_prob) > 0 else float("nan")

        # MC Dropout predictive entropy (T=10)
        T = 10
        enable_mc_dropout(model)
        entropies: list[float] = []
        with torch.no_grad():
            for batch in val_loader:
                images, _, labels, raw_metadata = batch
                images = images.to(device)
                metadata_tensor = metadata_batch_to_tensor(
                    raw_metadata, encoders, numeric_cols, cat_cols
                ).to(device)
                probs_T = []
                for _ in range(T):
                    _, p = model(images, metadata_tensor)
                    probs_T.append(p[:, 1].detach().cpu().numpy())
                P = np.stack(probs_T, axis=0).mean(axis=0)
                P = np.clip(P, 1e-6, 1 - 1e-6)
                ent = -(P * np.log(P) + (1 - P) * np.log(1 - P))
                entropies.extend(ent.tolist())
        avg_entropy = float(np.mean(entropies)) if entropies else float("nan")

        # MLflow: log calibration/uncertainty metrics
        if mlflow_active:
            try:
                mlflow_log_metrics({
                    "auc": float(auc),
                    "sensitivity": float(sens),
                    "specificity": float(spec),
                    "brier": float(brier),
                    "ece": float(ece),
                    "mc_dropout_entropy": float(avg_entropy),
                }, step=epoch + 1)
            except Exception:
                pass

        file_exists = calib_path.exists()
        with calib_path.open("a", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "epoch",
                    "auc",
                    "sensitivity",
                    "specificity",
                    "brier",
                    "ece",
                    "mc_dropout_entropy",
                ],
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow(
                {
                    "epoch": epoch + 1,
                    "auc": auc,
                    "sensitivity": sens,
                    "specificity": spec,
                    "brier": brier,
                    "ece": ece,
                    "mc_dropout_entropy": avg_entropy,
                }
            )

    # Traceability logging
        trace_dir = Path("logs"); trace_dir.mkdir(exist_ok=True)
        trace_file = trace_dir / "traceability.json"
        # Model hash
        state_bytes = b"".join([p.detach().cpu().numpy().tobytes() for p in model.state_dict().values()])
        model_hash = hashlib.sha256(state_bytes).hexdigest()[:16]
        record = {
            "event": "train_epoch",
            "epoch": epoch + 1,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "model_hash": model_hash,
            "train_loss": avg_train_loss,
            "val_loss": avg_val_loss,
            "val_acc": val_acc,
            "auc": auc,
            "ece": ece,
            "brier": brier,
            "mc_dropout_entropy": avg_entropy,
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

        # Log artifacts for this epoch (checkpoint); defer CSVs to end
        if mlflow_active:
            try:
                mlflow_log_artifacts([checkpoint_path])
            except Exception:
                pass

    print("Training complete. Latest metrics:")
    print(f"  Train loss: {avg_train_loss:.4f}")
    print(f"  Val loss:   {avg_val_loss:.4f}")
    print(f"  Val acc:    {val_acc:.3f}")

    # Log accumulated CSV artifacts and close MLflow run
    if mlflow_active:
        try:
            from src.logging_utils.mlflow_logger import log_artifacts as mlflow_log_artifacts, end_run as mlflow_end_run, set_tags as mlflow_set_tags
            # Set tags indicating readiness status
            mlflow_set_tags({"phase": "training", "regulatory_ready": False})
            mlflow_log_artifacts([metrics_path, Path("results")/"calibration_report.csv"])
            mlflow_end_run()
        except Exception:
            pass


if __name__ == "__main__":
    main()
