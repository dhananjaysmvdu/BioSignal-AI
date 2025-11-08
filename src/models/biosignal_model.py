"""Model definitions for multimodal skin lesion classification."""

from __future__ import annotations

from typing import Tuple

import timm
import torch
import torch.nn as nn
import torch.nn.functional as F


class MetadataEncoder(nn.Module):
    """Simple MLP that embeds tabular metadata into a compact representation."""

    def __init__(self, input_dim: int, hidden_dims: Tuple[int, int] = (128, 64), dropout: float = 0.2) -> None:
        super().__init__()
        if len(hidden_dims) != 2:
            raise ValueError("hidden_dims must contain exactly two layer sizes")

        self.input_dim = input_dim
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dims[0]),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(hidden_dims[0], hidden_dims[1]),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
        )
        self.output_dim = hidden_dims[-1]

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class FusionHead(nn.Module):
    """Fusion layers that combine visual and metadata embeddings for classification."""

    def __init__(self, input_dim: int, hidden_dim: int = 256, num_classes: int = 2) -> None:
        super().__init__()
        self.linear1 = nn.Linear(input_dim, hidden_dim)
        self.linear2 = nn.Linear(hidden_dim, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.linear1(x), inplace=True)
        return self.linear2(x)


class BioSignalModel(nn.Module):
    """Multimodal classifier merging EfficientNet image features with metadata embeddings."""

    def __init__(self, metadata_dim: int, metadata_hidden_dims: Tuple[int, int] = (128, 64), dropout: float = 0.2) -> None:
        super().__init__()

        self.image_encoder = timm.create_model(
            "efficientnet_b0",
            pretrained=True,
            num_classes=0,
            global_pool="avg",
        )
        self.visual_model = self.image_encoder
        visual_dim = self.image_encoder.num_features

        self.metadata_encoder = MetadataEncoder(metadata_dim, metadata_hidden_dims, dropout)
        self.metadata_input_dim = self.metadata_encoder.input_dim
        metadata_dim_out = self.metadata_encoder.output_dim

        fusion_input_dim = visual_dim + metadata_dim_out
        self.fusion_head = FusionHead(fusion_input_dim)

    def forward(self, image: torch.Tensor, metadata: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Return logits and probabilities for the provided inputs."""

        visual_features = self.image_encoder(image)
        metadata_features = self.metadata_encoder(metadata)
        combined = torch.cat((visual_features, metadata_features), dim=1)
        logits = self.fusion_head(combined)
        probabilities = F.softmax(logits, dim=1)
        return logits, probabilities

    @torch.no_grad()
    def predict(self, image: torch.Tensor, metadata: torch.Tensor) -> torch.Tensor:
        """Return probabilities under eval mode for inference use cases."""

        self.eval()
        _, probabilities = self.forward(image, metadata)
        return probabilities


if __name__ == "__main__":
    model = BioSignalModel(metadata_dim=12)
    model.eval()

    dummy_image = torch.rand(1, 3, 224, 224)
    dummy_metadata = torch.rand(1, 12)

    logits, probs = model(dummy_image, dummy_metadata)
    print(f"Logits shape: {logits.shape}")
    print(f"Probabilities shape: {probs.shape}")
    print(f"Probabilities: {probs.detach().cpu().numpy()}")
