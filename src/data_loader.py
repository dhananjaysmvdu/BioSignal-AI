"""Data ingestion utilities for downloading and preparing raw skin lesion datasets.

Extended to support ISIC 2018/2019 and HAM10000 dataset indexing.
Public dataset loaders assume images and metadata are already downloaded locally.
Expected directory layouts (customizable):

data/
    isic2019/
        metadata.csv  (must include image_path column relative to images/ subfolder or absolute)
        images/
    ham10000/
        metadata.csv
        images/

Use helper `build_dataset(csv, root)` to create a `SkinDataset`. CLI allows selection:
    python -m src.data_loader --dataset isic2019 --root data/isic2019
"""

from __future__ import annotations

from pathlib import Path
import random
import argparse
from typing import List, Tuple, Optional, Dict

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
import torch
from torch.utils.data import Dataset
from torchvision import transforms


def create_sample_dataset(output_dir: str | Path, n: int = 10) -> Path:
    """Create a toy dermoscopy dataset with synthetic images and metadata."""

    output_path = Path(output_dir)
    image_dir = output_path / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random()
    noise_rng = np.random.default_rng()

    genders = ["male", "female", "other"]
    lesion_sites = [
        "back",
        "face",
        "torso",
        "lower_extremity",
        "upper_extremity",
        "neck",
        "abdomen",
    ]
    labels = ["benign", "malignant"]

    records: List[dict[str, object]] = []

    for idx in range(n):
        filename = f"image_{idx:03d}.png"
        image_path = image_dir / filename

        base_color = np.array([rng.randint(60, 200) for _ in range(3)], dtype=np.uint8)
        canvas = np.tile(base_color, (256, 256, 1))
        noise = noise_rng.integers(0, 40, size=(256, 256, 3), dtype=np.uint8)
        canvas = np.clip(canvas + noise, 0, 255).astype(np.uint8)
        image = Image.fromarray(canvas, mode="RGB")

        overlay = ImageDraw.Draw(image)
        for _ in range(3):
            radius = rng.randint(10, 40)
            center = (rng.randint(20, 236), rng.randint(20, 236))
            bbox = [
                center[0] - radius,
                center[1] - radius,
                center[0] + radius,
                center[1] + radius,
            ]
            color = tuple(rng.randint(0, 255) for _ in range(3))
            overlay.ellipse(bbox, outline=color, width=2)

        image.save(image_path)

        record = {
            "image_path": str(Path("images") / filename),
            "age": rng.randint(18, 90),
            "gender": rng.choice(genders),
            "lesion_site": rng.choice(lesion_sites),
            "label": rng.choice(labels),
        }
        records.append(record)

    metadata = pd.DataFrame.from_records(records)
    csv_path = output_path / "metadata.csv"
    metadata.to_csv(csv_path, index=False)
    return csv_path


def _write_metadata_csv(frame: pd.DataFrame, out_csv: Path, image_root: Optional[Path] = None) -> Path:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if image_root is None:
        image_root = out_csv.parent / "images"
    # Ensure required columns
    cols = {c.lower(): c for c in frame.columns}
    # Normalize columns
    df = pd.DataFrame()
    # image_path
    if "image_path" in cols:
        df["image_path"] = frame[cols["image_path"]]
    elif "image" in cols:
        # add extension if missing by probing common extensions
        def to_path(x: str) -> str:
            p = Path(str(x))
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                for ext in (".jpg", ".jpeg", ".png"):
                    if (image_root / f"{p}{ext}").exists():
                        return str(Path("images")/f"{p}{ext}")
                # fallback
                return str(Path("images")/f"{p}.jpg")
            # make relative to images/
            if not p.is_absolute():
                return str(Path("images")/p.name)
            return str(p)
        df["image_path"] = frame[cols["image"]].astype(str).map(to_path)
    else:
        raise ValueError("Input metadata must have image_path or image column")

    # label
    if "label" in cols:
        df["label"] = frame[cols["label"]]
    elif "dx" in cols:
        # HAM10000 diagnosis; mark mel/bcc/akiec as malignant, others benign
        malignant = {"mel", "bcc", "akiec", "df", "vasc"}
        df["label"] = frame[cols["dx"]].astype(str).str.lower().map(lambda x: "malignant" if x in malignant else "benign")
    elif "mel" in cols:
        # ISIC 2019 one-hot target; treat MEL==1 as malignant else benign baseline
        df["label"] = frame[cols["mel"]].apply(lambda v: "malignant" if int(v)==1 else "benign")
    else:
        df["label"] = "benign"

    # demographics and site
    age_col = cols.get("age") or cols.get("age_approx")
    sex_col = cols.get("sex") or cols.get("gender")
    site_col = cols.get("anatom_site_general_challenge") or cols.get("lesion_site") or cols.get("localization")
    df["age"] = pd.to_numeric(frame.get(age_col, 0), errors="coerce").fillna(0).astype(int)
    df["gender"] = (
        frame.get(sex_col, "unknown").astype(str).str.strip().str.lower().replace({"nan": "unknown"})
    )
    df["lesion_site"] = (
        frame.get(site_col, "unknown").astype(str).str.strip().str.lower().replace({"nan": "unknown"})
    )

    df.to_csv(out_csv, index=False)
    return out_csv


def index_isic2019(root: Path) -> Path:
    """Construct metadata.csv for ISIC 2019 if training CSVs are present.

    Expected files (typical names):
      - ISIC_2019_Training_Metadata.csv
      - ISIC_2019_Training_GroundTruth.csv
      - images/ (folder with image files)
    """
    meta_csv = None
    gt_csv = None
    for p in root.glob("*.csv"):
        name = p.name.lower()
        if "metadata" in name:
            meta_csv = p
        if "groundtruth" in name:
            gt_csv = p
    if not meta_csv or not gt_csv:
        raise FileNotFoundError("Could not find ISIC 2019 metadata and ground truth CSVs in root")
    meta = pd.read_csv(meta_csv)
    gt = pd.read_csv(gt_csv)
    # Ensure common key
    key = "image" if "image" in gt.columns else list(set(gt.columns) & {"image_id", "image_name"})[0]
    if key not in meta.columns:
        # ISIC 2019 metadata may use 'image'
        if "image" in meta.columns:
            pass
        else:
            raise ValueError("No common key to merge ISIC 2019 CSVs")
    df = pd.merge(meta, gt, on=key, how="inner")
    # Normalize with helper
    out_csv = root / "metadata.csv"
    return _write_metadata_csv(df.rename(columns={key: "image"}), out_csv, image_root=root/"images")


def index_isic2018(root: Path) -> Path:
    """Construct metadata.csv for ISIC 2018 Task 3 if CSVs exist."""
    # Typical names
    meta_csv = next((p for p in root.glob("*Training_Metadata*.csv")), None)
    gt_csv = next((p for p in root.glob("*Training_GroundTruth*.csv")), None)
    if not meta_csv or not gt_csv:
        raise FileNotFoundError("Could not find ISIC 2018 CSVs in root")
    meta = pd.read_csv(meta_csv)
    gt = pd.read_csv(gt_csv)
    key = "image" if "image" in gt.columns else list(set(gt.columns) & {"image_id", "image_name"})[0]
    df = pd.merge(meta, gt, on=key, how="inner")
    out_csv = root / "metadata.csv"
    return _write_metadata_csv(df.rename(columns={key: "image"}), out_csv, image_root=root/"images")


def index_ham10000(root: Path) -> Path:
    """Construct metadata.csv for HAM10000 expected files: HAM10000_metadata.csv and images folder."""
    meta_csv = next((p for p in root.glob("*metadata*.csv")), None)
    if not meta_csv:
        raise FileNotFoundError("HAM10000 metadata CSV not found in root")
    meta = pd.read_csv(meta_csv)
    # HAM has 'image_id' and 'dx'
    if "image_id" in meta.columns and "image_path" not in meta.columns:
        meta = meta.assign(image=meta["image_id"].astype(str))
    out_csv = root / "metadata.csv"
    return _write_metadata_csv(meta, out_csv, image_root=root/"images")


class SkinDataset(Dataset):
    """Torch dataset for paired dermoscopy imagery and tabular metadata."""

    def __init__(
        self,
        csv_path: str | Path,
        *,
        image_root: str | Path | None = None,
        transform: transforms.Compose | None = None,
        return_raw_metadata: bool = False,
    ) -> None:
        self.csv_path = Path(csv_path)
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Metadata CSV not found: {self.csv_path}")

        self.image_root = Path(image_root) if image_root else self.csv_path.parent
        self.frame = pd.read_csv(self.csv_path)
        if "image_path" not in self.frame.columns:
            raise ValueError("metadata CSV must include an 'image_path' column")

        self.transform = transform or transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
                ),
            ]
        )

        self.gender_map = self._build_mapping("gender")
        self.site_map = self._build_mapping("lesion_site")
        self.label_map = self._build_mapping("label")
        self.return_raw_metadata = return_raw_metadata

    def __len__(self) -> int:
        return len(self.frame)

    def __getitem__(self, index: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        row = self.frame.iloc[index]

        image_path = Path(row["image_path"])
        if not image_path.is_absolute():
            image_path = self.image_root / image_path
        image = Image.open(image_path).convert("RGB")
        image_tensor = self.transform(image)

        age = float(row.get("age", 0.0))
        gender = str(row.get("gender", "unknown")).lower()
        lesion_site = str(row.get("lesion_site", "unknown")).lower()
        label = str(row.get("label", "benign")).lower()

        metadata_tensor = torch.tensor(
            [
                age,
                float(self.gender_map.get(gender, -1)),
                float(self.site_map.get(lesion_site, -1)),
            ],
            dtype=torch.float32,
        )

        label_tensor = torch.tensor(int(self.label_map.get(label, 0)), dtype=torch.long)

        if self.return_raw_metadata:
            raw_metadata = {
                "age": age,
                "gender": gender,
                "lesion_site": lesion_site,
                "label": label,
            }
            return image_tensor, metadata_tensor, label_tensor, raw_metadata

        return image_tensor, metadata_tensor, label_tensor

    def _build_mapping(self, column: str) -> dict[str, int]:
        values = (
            self.frame.get(column, pd.Series(dtype=str))
            .astype(str)
            .str.strip()
            .str.lower()
            .unique()
        )
        return {value: idx for idx, value in enumerate(sorted(values))}


def build_dataset(root: Path, dataset: str) -> SkinDataset:
    """Instantiate SkinDataset for supported dataset key.

    Args:
        root: Path to dataset root containing metadata.csv.
        dataset: One of {sample, isic2018, isic2019, ham10000}.
    """
    dataset = dataset.lower()
    if dataset == "sample":
        csv_path = root / "metadata.csv"
        if not csv_path.exists():
            print(f"Generating synthetic sample dataset at {root}...")
            csv_path = create_sample_dataset(root, n=128)
        return SkinDataset(csv_path)
    elif dataset in {"isic2018", "isic2019", "ham10000"}:
        csv_path = root / "metadata.csv"
        if not csv_path.exists():
            print(f"metadata.csv not found. Indexing {dataset} at {root} ...")
            if dataset == "isic2019":
                csv_path = index_isic2019(root)
            elif dataset == "isic2018":
                csv_path = index_isic2018(root)
            else:
                csv_path = index_ham10000(root)
        return SkinDataset(csv_path)
    else:
        raise ValueError(f"Unsupported dataset key: {dataset}")


def stratified_split_by_site(frame: pd.DataFrame, test_ratio: float = 0.2) -> Tuple[List[int], List[int]]:
    """Split indices so that each site contributes to both train/val where possible.

    Site column is inferred from common names: site|source_site|center|institution|dataset|collection_site.
    Falls back to random split when none found.
    """
    site_col_candidates = [
        "site",
        "source_site",
        "center",
        "institution",
        "dataset",
        "collection_site",
    ]
    site_col = next((c for c in site_col_candidates if c in frame.columns), None)
    if site_col is None:
        indices = list(range(len(frame)))
        random.shuffle(indices)
        split = int((1 - test_ratio) * len(indices))
        return indices[:split], indices[split:]

    train_idx: List[int] = []
    val_idx: List[int] = []
    for site, sub in frame.groupby(site_col):
        idxs = list(sub.index)
        random.shuffle(idxs)
        k = max(1, int(test_ratio * len(idxs)))
        val_idx.extend(idxs[:k])
        train_idx.extend(idxs[k:])
    if not train_idx or not val_idx:  # fallback
        indices = list(range(len(frame)))
        random.shuffle(indices)
        split = int((1 - test_ratio) * len(indices))
        return indices[:split], indices[split:]
    return train_idx, val_idx


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Skin dataset loader CLI")
    p.add_argument("--dataset", type=str, default="sample", help="Dataset key: sample|isic2018|isic2019|ham10000")
    p.add_argument("--root", type=Path, default=Path("data")/"sample", help="Root directory containing metadata.csv")
    p.add_argument("--show", action="store_true", help="Print first record summary")
    return p.parse_args()


def main_cli():
    args = parse_args()
    ds = build_dataset(args.root, args.dataset)
    print(f"Loaded dataset '{args.dataset}' with {len(ds)} samples from {args.root}")
    if args.show:
        img, meta, label = ds[0]
        print(f"Image shape: {img.shape}; Metadata: {meta.tolist()}; Label index: {int(label)}")


if __name__ == "__main__":
    main_cli()
