"""Data ingestion utilities for downloading and preparing raw skin lesion datasets."""

from __future__ import annotations

from pathlib import Path
import random
from typing import List, Tuple

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


if __name__ == "__main__":
    sample_dir = Path("data") / "sample"
    csv_file = sample_dir / "metadata.csv"
    if not csv_file.exists():
        print(f"Creating sample dataset at {sample_dir}...")
        csv_file = create_sample_dataset(sample_dir, n=12)

    dataset = SkinDataset(csv_file)
    print(f"Dataset size: {len(dataset)}")
    sample_image, sample_metadata, sample_label = dataset[0]
    print(f"Image tensor shape: {sample_image.shape}")
    print(f"Metadata tensor shape: {sample_metadata.shape}")
    print(f"Label tensor: {sample_label}")
