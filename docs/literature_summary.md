Evaluation Report Generated on: 2025-11-08 20:25 UTC

# BioSignal-X Literature Review (2022–2025)

This document surveys recent high-impact publications across multimodal dermatology AI, transformer-based imaging, clinical validation/regulation, explainability, and dataset bias/calibration.

---
## 1. Multimodal Skin Lesion Classification (Image + Metadata Fusion)
| Title | Authors | Year | Venue | Dataset / N | Architecture | Key Metrics | Limitations / Bias | DOI / Link |
|-------|---------|------|-------|-------------|--------------|-------------|--------------------|------------|
| PLACEHOLDER 1 | ... | 2023 | ... | ISIC 2020 / ~Xk | EfficientNet + Tabular MLP | AUC: -, Sens: -, Spec: - | Demographic imbalance | DOI: |
| PLACEHOLDER 2 | ... | 2024 | ... | HAM10000 / 10k | ResNet + Metadata Fusion | AUC: -, F1: - | Small rare class counts | DOI: |
| PLACEHOLDER 3 | ... | 2025 | ... | ISIC Combined / ~60k | ViT Hybrid Fusion | AUC: -, Sens: -, ECE: - | Calibration drift | DOI: |
| PLACEHOLDER 4 | ... | 2022 | ... | Private Dermoscopy / ~5k | DenseNet + Clinical Fields | AUC: - | Limited external validation | DOI: |
| PLACEHOLDER 5 | ... | 2024 | ... | ISIC + External | Multi-Task Fusion Net | AUC: -, F1: - | Metadata missingness | DOI: |

## 2. Transformer-Based Medical Imaging (ViT, ConvNeXt, Hybrid CNNs)
| Title | Authors | Year | Venue | Modality / Dataset | Architecture | Key Metrics | Limitations | DOI / Link |
|-------|---------|------|-------|--------------------|--------------|-------------|------------|------------|
| PLACEHOLDER 6 | ... | 2023 | ... | Dermoscopy / ISIC | ViT-B Patch16 | AUC: - | High compute cost | DOI: |
| PLACEHOLDER 7 | ... | 2024 | ... | Histopath / TCGA | ConvNeXt-L | F1: - | Overfitting small cohorts | DOI: |
| PLACEHOLDER 8 | ... | 2025 | ... | Multi-modal | Hybrid CNN+Transformer | AUC: -, ECE: - | Domain shift | DOI: |
| PLACEHOLDER 9 | ... | 2022 | ... | OCT / ~N | Swin Transformer | AUC: - | Limited interpretability | DOI: |
| PLACEHOLDER 10 | ... | 2024 | ... | Dermoscopy | Hierarchical ViT | AUC: -, Brier: - | Data scarcity | DOI: |

## 3. Clinical Validation & Regulatory Pathways (FDA, ISO 13485, SaMD)
| Title | Authors | Year | Venue | Focus | Dataset / Study Design | Key Points | Limitations | DOI / Link |
|-------|---------|------|-------|-------|------------------------|-----------|------------|------------|
| PLACEHOLDER 11 | ... | 2023 | ... | FDA SaMD Guidance | Narrative Review | Emphasizes post-market surveillance | Regulatory updates pending | DOI: |
| PLACEHOLDER 12 | ... | 2024 | ... | ISO 13485 Compliance | Case Study | Quality management integration | Lack of dermoscopy specifics | DOI: |
| PLACEHOLDER 13 | ... | 2025 | ... | Clinical Trial Framework | Prospective Reader Study | Multi-reader multi-case design | Small institution sample | DOI: |
| PLACEHOLDER 14 | ... | 2022 | ... | Risk Stratification | Retrospective | Need for bias audits | Sparse demographic annotation | DOI: |
| PLACEHOLDER 15 | ... | 2024 | ... | SaMD Lifecycle | White Paper | Continuous learning governance | Unclear performance thresholds | DOI: |

## 4. Explainability (Grad-CAM, SHAP, Uncertainty)
| Title | Authors | Year | Venue | Method | Dataset | Metrics Reported | Limitations / Bias | DOI / Link |
|-------|---------|------|-------|--------|---------|------------------|--------------------|------------|
| PLACEHOLDER 16 | ... | 2023 | ... | Grad-CAM variants | ISIC | Intersection Over Union (IOU) | Visual artifacts | DOI: |
| PLACEHOLDER 17 | ... | 2024 | ... | SHAP for Images | HAM10000 | AUC: -, SHAP impact | Computationally expensive | DOI: |
| PLACEHOLDER 18 | ... | 2025 | ... | Uncertainty Ensembles | ISIC | AUC: -, ECE: - | Poor rare class calibration | DOI: |
| PLACEHOLDER 19 | ... | 2022 | ... | Attention Maps | Private | Qualitative overlays | Lack quantitative eval | DOI: |
| PLACEHOLDER 20 | ... | 2024 | ... | Bayesian CNN | ISIC | Brier: -, NLL: - | High variance | DOI: |

## 5. Dataset Bias, Calibration & Generalization
| Title | Authors | Year | Venue | Dataset Scope | Bias Dimension | Key Findings | Impact | DOI / Link |
|-------|---------|------|-------|--------------|---------------|-------------|-------|------------|
| PLACEHOLDER 21 | ... | 2023 | ... | ISIC Skin Types | Fitzpatrick imbalance | AUC drop in dark skin | Equity concerns | DOI: |
| PLACEHOLDER 22 | ... | 2024 | ... | Multi-Center Dermoscopy | Device variability | Domain shift reduces sensitivity | Generalization risk | DOI: |
| PLACEHOLDER 23 | ... | 2025 | ... | HAM10000 + External | Label noise | F1 degradation | Need robust loss | DOI: |
| PLACEHOLDER 24 | ... | 2022 | ... | ISIC Longitudinal | Temporal drift | Calibration decay | Requires recalibration | DOI: |
| PLACEHOLDER 25 | ... | 2024 | ... | Diverse Cohort | Age/sex distribution | Stratified performance gaps | Bias mitigation needed | DOI: |
| PLACEHOLDER 26 | ... | 2025 | ... | Federated Dermoscopy | Site heterogeneity | Mixed-site training improves AUC | Privacy trade-offs | DOI: |
| PLACEHOLDER 27 | ... | 2023 | ... | Pseudo-Labels Study | Semi-supervised | Gains plateau after X% unlabeled | Quality threshold | DOI: |
| PLACEHOLDER 28 | ... | 2024 | ... | Calibration Methods | ISIC | ECE comparisons | Temperature scaling best | DOI: |
| PLACEHOLDER 29 | ... | 2025 | ... | External Validation | Multi-region | Performance variance | Need external test sets | DOI: |
| PLACEHOLDER 30 | ... | 2022 | ... | Metadata Quality | Mixed sources | Missingness harms fusion | Data completeness | DOI: |

---
## Synthesis & Gaps
- Multimodal fusion improves discriminative performance but is sensitive to metadata quality and missingness.
- Transformer variants show promise yet increase computational and data demands.
- Regulatory alignment demands prospective validation, bias audits, and lifecycle monitoring.
- Explainability methods lack standardized quantitative evaluation; uncertainty integration remains underused.
- Calibration and demographic fairness are recurring weak points needing systematic reporting.

## Recommendations for BioSignal-X
1. Prioritize external validation on ISIC and at least one multi-center dataset.
2. Integrate uncertainty estimates (e.g., MC Dropout, deep ensembles) into inference pipeline.
3. Add automated calibration reporting (ECE, Brier) post-training.
4. Introduce metadata missingness robustness tests and imputation strategies.
5. Prepare documentation aligning with FDA SaMD guidance for potential translational pathways.
