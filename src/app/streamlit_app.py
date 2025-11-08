"""Streamlit application entry point for BioSignal-AI inference."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import streamlit as st
import torch
import torch.nn.functional as F
from PIL import Image

from src.models.biosignal_model import BioSignalModel
from src.preprocess import load_metadata_encoders, transform_metadata
from src.utils.gradcam import GradCAM, apply_heatmap_on_image


@st.cache_resource(show_spinner=False)
def load_model(metadata_dim: int, checkpoint_dir: Path) -> BioSignalModel:
    model = BioSignalModel(metadata_dim=metadata_dim)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    checkpoints = sorted(checkpoint_dir.glob("model_epoch*.pt"))
    if checkpoints:
        latest = checkpoints[-1]
        try:
            state = torch.load(latest, map_location=device)
            load_result = model.load_state_dict(state.get("model_state", {}), strict=False)
            warning_msgs = []
            if load_result.missing_keys:
                warning_msgs.append(f"Missing keys: {', '.join(load_result.missing_keys[:5])}")
            if load_result.unexpected_keys:
                warning_msgs.append(f"Unexpected keys: {', '.join(load_result.unexpected_keys[:5])}")
            if warning_msgs:
                st.sidebar.warning(
                    "Checkpoint partially loaded (inference will continue): " + "; ".join(warning_msgs)
                )
            else:
                st.sidebar.success(f"Loaded checkpoint: {latest.name}")
        except Exception as exc:  # pylint: disable=broad-except
            st.sidebar.warning(f"Failed to load checkpoint {latest.name}: {exc}")
    else:
        st.sidebar.info("No checkpoints found. Using randomly initialized weights.")

    model.eval()
    return model


def load_encoders(artifact_dir: Path) -> Dict[str, object]:
    try:
        encoders = load_metadata_encoders(save_dir=artifact_dir)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "Metadata encoders not found. Run preprocessing pipeline (src/preprocess.py)."
        ) from exc
    return encoders


def preprocess_metadata(encoders: Dict[str, object], age: int, gender: str, lesion_site: str) -> torch.Tensor:
    scaler = encoders["scaler"]
    encoder = encoders["encoder"]
    numeric_cols = list(getattr(scaler, "feature_names_in_", ["age"]))
    cat_cols = list(getattr(encoder, "feature_names_in_", ["gender", "lesion_site"]))

    data = pd.DataFrame(
        [
            {
                "age": age,
                "gender": gender.lower(),
                "lesion_site": lesion_site.lower(),
            }
        ]
    )
    for col in numeric_cols:
        if col not in data.columns:
            data[col] = 0
    for col in cat_cols:
        if col not in data.columns:
            data[col] = "unknown"
    data = data[numeric_cols + cat_cols]

    return transform_metadata(data, encoders, numeric_cols, cat_cols)


def preprocess_image(image: Image.Image) -> torch.Tensor:
    image = image.convert("RGB").resize((224, 224))
    arr = np.asarray(image).astype(np.float32) / 255.0
    arr = (arr - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
    arr = np.transpose(arr, (2, 0, 1))
    return torch.tensor(arr, dtype=torch.float32).unsqueeze(0)


def run_inference(
    model: BioSignalModel,
    image_tensor: torch.Tensor,
    metadata_tensor: torch.Tensor,
) -> Dict[str, torch.Tensor]:
    device = next(model.parameters()).device
    image_tensor = image_tensor.to(device)
    metadata_tensor = metadata_tensor.to(device)
    logits, probs = model(image_tensor, metadata_tensor)
    predicted_idx = probs.argmax(dim=1).item()
    return {
        "logits": logits.detach().cpu(),
        "probs": probs.detach().cpu().squeeze(0),
        "pred_idx": predicted_idx,
    }


def generate_overlay(
    model: BioSignalModel,
    image_tensor: torch.Tensor,
    metadata_tensor: torch.Tensor,
    original_image: Image.Image,
) -> Image.Image:
    gradcam = GradCAM(model, metadata_dim=metadata_tensor.shape[1])
    gradcam.forward(image_tensor.to(next(model.parameters()).device), metadata_tensor)
    heatmap = gradcam.generate_heatmap()
    return apply_heatmap_on_image(original_image, heatmap)


def build_report(prediction: str, probabilities: Dict[str, float]) -> bytes:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pylint: disable=broad-except
        raise ImportError("reportlab is required for PDF export. Install via pip install reportlab.") from exc

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, height - 72, "BioSignal-AI Inference Report")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, height - 110, f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}")
    pdf.drawString(72, height - 140, f"Predicted Class: {prediction}")

    pdf.drawString(72, height - 170, "Probabilities:")
    y_offset = height - 190
    for label, prob in probabilities.items():
        pdf.drawString(90, y_offset, f"{label.title()}: {prob:.3f}")
        y_offset -= 18

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.read()


def main() -> None:
    st.set_page_config(page_title="BioSignal-AI", layout="wide")
    st.title("BioSignal-AI: Multimodal Skin Lesion Classifier")

    artifact_dir = Path("artifacts")
    checkpoint_dir = Path("checkpoints")

    # Sidebar inputs
    st.sidebar.header("Input Data")
    image_file = st.sidebar.file_uploader("Upload lesion image", type=["jpg", "jpeg", "png"])
    age = st.sidebar.number_input("Age", min_value=0, max_value=120, value=45, step=1)
    gender = st.sidebar.selectbox("Gender", options=["male", "female", "other"], index=0)
    lesion_site = st.sidebar.selectbox(
        "Lesion Site",
        options=["back", "face", "torso", "lower_extremity", "upper_extremity", "neck"],
        index=0,
    )

    analyze = st.sidebar.button("Analyze", use_container_width=True)

    if analyze:
        if image_file is None:
            st.error("Please upload a lesion image before analysis.")
            return

        try:
            encoders = load_encoders(artifact_dir)
        except FileNotFoundError as exc:
            st.error(str(exc))
            return

        metadata_tensor = preprocess_metadata(encoders, int(age), gender, lesion_site)
        metadata_dim = metadata_tensor.shape[1]

        model = load_model(metadata_dim, checkpoint_dir)

        original_image = Image.open(image_file)
        image_tensor = preprocess_image(original_image)

        try:
            outputs = run_inference(model, image_tensor, metadata_tensor)
        except Exception as exc:  # pylint: disable=broad-except
            st.error(f"Inference failed: {exc}")
            return

        labels = ["benign", "malignant"]
        prediction = labels[outputs["pred_idx"]]
        probabilities = {label: outputs["probs"][idx].item() for idx, label in enumerate(labels)}

        try:
            overlay = generate_overlay(model, image_tensor, metadata_tensor, original_image)
        except Exception as exc:  # pylint: disable=broad-except
            st.warning(f"Grad-CAM generation failed: {exc}")
            overlay = None

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Prediction")
            st.success(f"Predicted class: {prediction.title()}")
            st.bar_chart(pd.DataFrame([probabilities], index=["Probability"]).T)

        with col2:
            st.subheader("Grad-CAM Overlay")
            if overlay is not None:
                st.image(overlay, caption="Grad-CAM Heatmap", use_column_width=True)
            else:
                st.info("Grad-CAM overlay unavailable.")

        if st.button("Download Report (PDF)", use_container_width=True):
            try:
                pdf_bytes = build_report(prediction.title(), probabilities)
                st.download_button(
                    label="Download Report", data=pdf_bytes, file_name="biosignal_ai_report.pdf", mime="application/pdf"
                )
            except ImportError as exc:
                st.error(str(exc))
            except Exception as exc:  # pylint: disable=broad-except
                st.error(f"Failed to generate report: {exc}")

    st.caption("Research prototype. Not for clinical use.")


if __name__ == "__main__":
    main()
