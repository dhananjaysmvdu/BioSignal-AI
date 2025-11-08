"""Grad-CAM visualization helpers for interpreting convolutional models."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import pandas as pd
from PIL import Image
import torch

from src.preprocess import load_metadata_encoders, transform_metadata, fit_metadata_encoders
from src.data_loader import SkinDataset


class GradCAM:
    """Compute Grad-CAM heatmaps for convolutional layers."""

    def __init__(
        self,
        model: torch.nn.Module,
        target_layer: Optional[torch.nn.Module] = None,
        metadata_dim: Optional[int] = None,
    ) -> None:
        self.model = model.eval()
        self.target_layer = target_layer or self._infer_target_layer()

        encoder_module = getattr(model, "metadata_encoder", None)
        inferred_dim = metadata_dim or getattr(model, "metadata_input_dim", None) or getattr(encoder_module, "input_dim", None)
        if inferred_dim is None:
            raise ValueError("Unable to infer metadata_dim for Grad-CAM; specify explicitly.")
        self.metadata_dim = inferred_dim

        self.activations: Optional[torch.Tensor] = None
        self.gradients: Optional[torch.Tensor] = None
        self.hook_handles: list = []
        self._register_hooks()

    def _infer_target_layer(self) -> torch.nn.Module:
        visual_model = getattr(self.model, "visual_model", None)
        if visual_model is None:
            raise AttributeError("Model does not expose a visual_model attribute required for Grad-CAM.")
        if not hasattr(visual_model, "conv_head"):
            raise AttributeError("visual_model lacks conv_head layer expected for EfficientNet-B0.")
        return visual_model.conv_head

    def _register_hooks(self) -> None:
        def forward_hook(module, _inputs, outputs):
            self.activations = outputs.detach()

        def backward_hook(module, _grad_inputs, grad_outputs):
            self.gradients = grad_outputs[0].detach()

        self.hook_handles.append(self.target_layer.register_forward_hook(forward_hook))
        self.hook_handles.append(self.target_layer.register_full_backward_hook(backward_hook))

    def forward(
        self,
        image_tensor: torch.Tensor,
        metadata_tensor: Optional[torch.Tensor] = None,
        class_idx: Optional[int] = None,
    ) -> torch.Tensor:
        if metadata_tensor is None:
            metadata_tensor = torch.zeros(image_tensor.size(0), self.metadata_dim, device=image_tensor.device)

        self.model.zero_grad(set_to_none=True)
        logits, _ = self.model(image_tensor, metadata_tensor)

        if class_idx is None:
            class_idx_tensor = logits.argmax(dim=1)
        elif isinstance(class_idx, int):
            class_idx_tensor = torch.full((logits.size(0),), class_idx, device=logits.device, dtype=torch.long)
        else:
            class_idx_tensor = torch.as_tensor(class_idx, device=logits.device, dtype=torch.long)
            if class_idx_tensor.ndim == 0:
                class_idx_tensor = class_idx_tensor.repeat(logits.size(0))

        score = logits.gather(1, class_idx_tensor.view(-1, 1)).sum()
        score.backward(retain_graph=True)
        return logits

    def generate_heatmap(self) -> np.ndarray:
        if self.gradients is None or self.activations is None:
            raise RuntimeError("Gradients or activations not captured. Call forward() before generate_heatmap().")

        gradients = self.gradients.mean(dim=(2, 3), keepdim=True)
        weighted = gradients * self.activations
        heatmap = weighted.sum(dim=1).squeeze(0)
        heatmap = torch.relu(heatmap)
        heatmap -= heatmap.min()
        heatmap /= (heatmap.max() + 1e-8)
        return heatmap.cpu().numpy()

    def __del__(self):
        for handle in self.hook_handles:
            handle.remove()


def apply_heatmap_on_image(original_image: Image.Image, heatmap: np.ndarray, alpha: float = 0.4) -> Image.Image:
    resized_heatmap = cv2.resize(heatmap, (original_image.width, original_image.height))
    heatmap_uint8 = np.uint8(255 * resized_heatmap)
    heatmap_color = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)
    heatmap_color = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2RGB)

    original = np.array(original_image)
    overlay = cv2.addWeighted(heatmap_color, alpha, original, 1 - alpha, 0)
    return Image.fromarray(overlay)


if __name__ == "__main__":
    sample_dir = Path("data") / "sample"
    metadata_path = sample_dir / "metadata.csv"
    if not metadata_path.exists():
        raise FileNotFoundError("metadata.csv not found. Run src/data_loader.py to generate data.")

    dataset = SkinDataset(metadata_path, return_raw_metadata=True)
    image_tensor, _, _, raw_metadata = dataset[0]

    try:
        encoders = load_metadata_encoders()
    except FileNotFoundError:
        print("Encoders not found; fitting from sample metadata.")
        frame = dataset.frame
        encoders = fit_metadata_encoders(frame, numeric_cols=["age"], cat_cols=["gender", "lesion_site"])[1]

    numeric_cols = list(encoders["scaler"].feature_names_in_)
    cat_cols = list(encoders["encoder"].feature_names_in_)

    metadata_frame = pd.DataFrame([raw_metadata])
    for col in numeric_cols:
        metadata_frame[col] = pd.to_numeric(metadata_frame.get(col, 0), errors="coerce").fillna(0)
    for col in cat_cols:
        metadata_frame[col] = metadata_frame.get(col, "unknown").fillna("unknown").astype(str)
    metadata_frame = metadata_frame[numeric_cols + cat_cols]
    metadata_tensor = transform_metadata(
        metadata_frame,
        encoders,
        numeric_cols,
        cat_cols,
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    metadata_tensor = metadata_tensor.to(device)
    image_batch = image_tensor.unsqueeze(0).to(device)

    from src.models.biosignal_model import BioSignalModel

    metadata_dim = metadata_tensor.shape[1]
    model = BioSignalModel(metadata_dim=metadata_dim).to(device)

    gradcam = GradCAM(model, metadata_dim=metadata_dim)
    gradcam.forward(image_batch, metadata_tensor)
    heatmap = gradcam.generate_heatmap()

    original_image_path = sample_dir / dataset.frame.iloc[0]["image_path"]
    original_image = Image.open(original_image_path).convert("RGB")
    blended = apply_heatmap_on_image(original_image, heatmap)

    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    output_path = results_dir / "gradcam_test.png"
    blended.save(output_path)
    print(f"Grad-CAM overlay saved to {output_path}")
