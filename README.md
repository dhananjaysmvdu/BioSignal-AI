---
title: "BioSignal-X: AI-Powered Biomedical Signal Analysis"
tags: ["streamlit", "biosignals", "deep-learning", "explainable-ai", "healthcare"]
license: "mit"
datasets: []
author: "Mrityunjay Dhananjay"
---

# BioSignal-AI

[![Hugging Face Spaces](https://img.shields.io/badge/%F0%9F%A4%97%20View%20on%20Hugging%20Face%20Spaces-blue)](https://huggingface.co/spaces/LogDMax/BioSignal-X) [![CI](https://img.shields.io/badge/CI-pending-lightgrey.svg)](#) [![License](https://img.shields.io/badge/license-Apache--2.0-lightgrey.svg)](#)

<!-- COVERAGE_BADGE:BEGIN -->
![Coverage](badges/coverage.svg)
<!-- COVERAGE_BADGE:END -->

![Integrity](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/dhananjaysmvdu/BioSignal-AI/main/badges/integrity_status.json)
![Reproducibility](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/dhananjaysmvdu/BioSignal-AI/main/badges/reproducibility_status.json)

> **Governance Health:** Live integrity and reproducibility scores updated with each release.  
> Scores ≥90 = 🟢 High Integrity | 70–89 = 🟡 Stable | <70 = 🔴 Review Required

<!-- REGIME_ALERT_BADGE:BEGIN -->
Regime Stability: Stable (RSI 100%) — last update pending next scheduled governance audit.
<!-- REGIME_ALERT_BADGE:END -->

*Multimodal dermatology research toolkit for pairing dermoscopy imagery with contextual patient data.*

## Research Abstract
BioSignal-X advances biomedical AI by fusing dermoscopic imagery with patient metadata to train multimodal classifiers capable of nuanced lesion assessment. The platform integrates Grad-CAM visualization for interpretability, Streamlit for interactive analysis, and Hugging Face Spaces for accessible deployment—supporting rapid experimentation and transparent clinical research workflows.

## Key Features
- Multimodal learning pipeline combining image embeddings with tabular biosignal metadata
- Explainability via Grad-CAM overlays and PDF report generation
- Real-time inference delivered through a Streamlit user interface
- Seamless deployment to Hugging Face Spaces with automated CI triggers
- Biomedical research alignment with reproducible preprocessing and training utilities

## Model Card
**Architecture:** BioSignal-X integrates an EfficientNet-B0 visual backbone with a metadata fusion layer, enabling joint processing of dermoscopic images and demographic or clinical features.  
**Input Format:** RGB lesion images (224×224) with associated metadata tensors.  
**Output:** Binary or multiclass prediction logits and Grad-CAM heatmaps visualizing model focus regions.  
**Training Data:** Synthetic data generated for development; future versions target open biomedical datasets such as ISIC 2019 (skin lesions) and PhysioNet signals.  
**Intended Use:** Biomedical education, interpretability research, and AI-driven visualization — *not for diagnostic use.*

## Dataset
Current version uses synthetic datasets to simulate real-world variability.  
Future integration planned with:
- [ISIC 2019 Challenge Dataset](https://challenge.isic-archive.com/data/)
- [PhysioNet Biomedical Signals](https://physionet.org/)  
Users may fine-tune or replace datasets through configurable `data_loader.py`.

## Ethical Considerations
BioSignal-X is a research and educational framework. Predictions are not validated for clinical application.  
The project encourages responsible use of medical AI, transparency in model interpretability, and fairness across demographic groups.  
Any deployment in healthcare contexts must follow institutional review and regulatory standards.

## Clinical Validation
- External cohort evaluation via `clinical_validation/validate_clinical.py` with MC Dropout uncertainty and per-case JSON outputs.
- Group-level summaries by site and demographics (sex, age bins, skin type where available).
- Inter-site variance analysis in `benchmarks/compare_baselines.ipynb` produces CSV and boxplot artifacts.

## MLflow Experiment Tracking
Optional MLflow integration logs hyperparameters, per-epoch metrics (loss, accuracy, AUC, ECE, Brier, MC Dropout entropy), and artifacts (checkpoints, calibration CSVs, clinical validation outputs). Enable with `--mlflow` flag after setting `MLFLOW_TRACKING_URI` and optional `MLFLOW_EXPERIMENT` environment variables.

Example (PowerShell):
```
$env:MLFLOW_TRACKING_URI="http://localhost:5000"; $env:MLFLOW_EXPERIMENT="BioSignalX"; python train.py --epochs 5 --mlflow
```

## Drift Detection
Automated cohort shift monitoring via `monitoring/drift_detector.py` computes Jensen–Shannon divergence across numeric (e.g., age) and categorical (e.g., lesion_site, gender) features.

Run a drift check comparing a historical reference vs current intake:
```
python -m monitoring.drift_detector --ref data/reference/metadata.csv --cur data/current/metadata.csv --out logs/drift_report.json
```
Outputs a JSON report with per-feature scores and an overall drift rate suitable for scheduled jobs (e.g., weekly CI).

## Evaluation Report Notebook
Notebook `notebooks/generate_eval_report.ipynb` (planned) will aggregate calibration (`results/calibration_report.csv`), fairness, inter-site variability, and clinical validation summaries into a consolidated PDF/table bundle for publication or internal review.

## Regulatory Alignment
- See `docs/compliance_guidelines.md` for SaMD, EU MDR, and ISO references with capability mapping.
- Calibration reporting (ECE, Brier), traceability logs, and versioned artifacts support reproducibility.

## Governance & Traceability
- Training logs: `results/calibration_report.csv`, `checkpoints/metrics.csv`.
- Traceability: `logs/traceability.json` records model hash, config, dataset, and timestamps.
- Literature and experimental roadmap guide bias audits and reader study planning.

### Reflex Integrity Sentinel Scoring
Integrity = 100 − (Σ violations × 15 + Σ warnings × 2.5)

Notes:
• Violations represent critical rule breaches (e.g., missing required artifacts, non-monotonic timestamps, data integrity failures, parameter incoherence). Each violation deducts 15 points.
• Warnings represent tolerable inconsistencies (e.g., minor cross-validation mismatches, insufficient history, missing optional fields). Each warning deducts 2.5 points.
• Score is clamped to [0, 100].

Adaptive-learning gates below 70 are skipped for safety.

## Post-Market Surveillance (Planned)
Upcoming modules will extend drift detection, adverse event logging, and periodic performance re-evaluation aligned with ISO 14971 risk controls and IEC 62304 maintenance procedures.

## Citation
If you use BioSignal-X in your research, please cite using the included `CITATION.cff` file or the following:

```bibtex
@software{dhananjay2025biosignalx,
	author = {Dhananjay, Mrityunjay},
	title = {BioSignal-X: AI-Powered Biomedical Signal Analysis and Visualization},
	year = {2025},
	url = {https://huggingface.co/spaces/LogDMax/BioSignal-X}
}
```

**Governance Whitepaper:** For a formal description of the Reflex Governance Architecture, see [`docs/GOVERNANCE_WHITEPAPER.md`](docs/GOVERNANCE_WHITEPAPER.md). This IEEE/ACM-style document describes the self-verifying feedback system, schema provenance ledger, and adaptive control mechanisms. Cite as:

> Reflex Governance Architecture: Self-Verifying Adaptive Control System, v1.0  
> DOI: https://doi.org/10.5281/zenodo.14173152
> Repository: https://github.com/dhananjaysmvdu/BioSignal-AI

### Governance Bulletins
Quarterly summaries of governance health, integrity trends, and reproducibility certification status:
- **[Q4 2025 Bulletin](docs/quarterly/GOVERNANCE_SUMMARY_Q4_2025.md)** — v1.0.0-Whitepaper release metrics, DOI integration, and operational continuity

### Live Governance Portal
Real-time transparency dashboard with live integrity, reproducibility, and provenance metrics:
- **[🔬 Governance Portal](portal/index.html)** — Interactive dashboard with automated metrics updates

- **Explore Calibration & Research Portal:**
  - Calibration: `portal/calibration.html` — CE/FB metrics and forecast vs actual analysis
  - Publications & Datasets: `portal/publications.html` — DOIs and searchable datasets

### Forecast Risk Scoring
Predictive governance intelligence with automated risk evaluation:
- **Forecast Deviation Index (FDI)**: Measures prediction accuracy as `|predicted - actual| / predicted × 100`
  - Excellent: FDI < 5% (strong model performance)
  - Good: FDI < 10% (acceptable accuracy)
  - Drifting: FDI ≥ 10% (requires recalibration)
- **Confidence Stability (CS)**: Tracks forecast confidence variance (rolling std, window=10)
  - Stable: CS < 3.0 (low variance)
  - Unstable: CS ≥ 5.0 (high variance, review model inputs)
- **Current Status**: FDI = 0.0% (Excellent), CS = 2.1 (Stable)
- **Updates**: Twice weekly (Tuesday/Friday 00:30 UTC) via Meta-Forecast 2.0 engine

See [`reports/forecast_risk_assessment.json`](reports/forecast_risk_assessment.json) for full risk assessment details.

### Next Release Roadmap
Development planning for upcoming enhancements:
- **[v1.1 Release Planning](planning/RELEASE_PLANNING_v1.1.md)** — Meta-Forecast 2.0, adaptive feedback refinement, performance optimization (Target: Q1 2026)

## Project Overview
- **Title:** BioSignal-X
- **Description:** AI-driven biosignal analysis platform integrating deep learning with biomedical data visualization and explainability (Grad-CAM).
- **Deployed at:** https://huggingface.co/spaces/LogDMax/BioSignal-X
- **Maintainer:** dhananjaysmvdu
- **License:** MIT

## Launch Demo
- Explore the live application on Hugging Face Spaces: https://huggingface.co/spaces/LogDMax/BioSignal-X

## Problem Statement
Dermatology lacks reproducible baselines for combining dermoscopic images with metadata such as demographics, lesion history, and acquisition context. BioSignal-AI aims to deliver a research-grade pipeline that ingests paired inputs, harmonizes modalities, and trains classifiers capable of leveraging both visual and tabular signals for skin lesion risk stratification.

## Datasets
We focus on ISIC Archive releases and HAM10000. Download scripts are provided in `src/data_loader.py`; supply dataset aliases and destinations through its CLI to maintain consistent folder conventions and metadata schemas.

## Quick Start
1. `python -m venv .venv`
2. `.venv\Scripts\Activate.ps1`
3. `pip install -r requirements.txt`
4. `python src\data_loader.py --dataset ISIC --split sample`
5. `python train.py --epochs 1`

## Streamlit App
`streamlit run app.py`

## Folder Structure
```
BioSignal-AI/
├─ app.py
├─ requirements.txt
├─ src/
│  ├─ data_loader.py
│  ├─ models/
│  └─ utils/
├─ train.py
└─ README.md
```

## How to Contribute
1. Clone with GitHub Desktop for commit history clarity.
2. Create a feature branch named after your issue (e.g., `feature/metadata-parsing`).
3. Commit focused changes, sync, and open a pull request detailing datasets and experiments touched.
4. Request at least one review before merging.

## Ethical Use & Citation
BioSignal-AI is a research prototype only; it is **not** validated for clinical diagnosis, triage, or therapeutic decisions. Always consult board-certified dermatologists when interpreting results. If you publish work derived from this repository, cite the tool as: “BioSignal-AI: Multimodal Skin Lesion Classification Toolkit (2025).” When sharing findings, disclose dataset biases, annotation quality, and any demographic limitations observed during evaluation.

Triggered Hugging Face deployment via Copilot Agent.
✅ Redeployment triggered by Copilot Agent — target Space: LogDMax/BioSignal-X.

## Author & Acknowledgment
**Project Lead & Developer:** Mrityunjay Dhananjay  
B.Sc. (Hons) Biomedical Science, Acharya Narendra Dev College, University of Delhi  

BioSignal-X was conceptualized, developed, and deployed by Mrityunjay Dhananjay.  
The project integrates biomedical AI research, explainable deep learning, and multimodal data visualization through Streamlit and Hugging Face Spaces.  
Special thanks to the open-source community and free research tools that made this project possible.