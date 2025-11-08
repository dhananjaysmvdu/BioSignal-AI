# BioSignal-X Experimental Roadmap

## 1. Objectives
- Establish reproducible multimodal benchmarks (image + metadata) on ISIC and HAM10000.
- Evaluate generalization via external validation on multi-center dermoscopy datasets.
- Integrate uncertainty quantification (deep ensembles, MC Dropout) and calibration reporting.
- Conduct a reader study comparing clinician vs. model performance with interpretability overlays.

## 2. Dataset Acquisition Plan
| Dataset | Scope | Actions | Risks | Mitigation |
|---------|-------|---------|-------|-----------|
| ISIC 2019 | Skin lesion images + metadata | Download, normalize metadata fields | Inconsistent annotations | Schema harmonization script |
| HAM10000 | Multi-source dermoscopy | Merge with ISIC subset for diversity | Class imbalance | Weighted loss, focal loss |
| External Multi-Center | Diverse devices/sites | Partnership / data request | Access delays | Start early outreach |
| PhysioNet Signals (Future) | Biosignals for fusion | Identify relevant subset | Domain mismatch | Pilot feasibility study |

## 3. Study Design
### 3.1 Model Development
- Baseline: EfficientNet-B0 + tabular MLP fusion.
- Variants: ViT fusion, ConvNeXt fusion, Meta-transformer adaptor.
- Losses: Cross-entropy, focal loss for imbalance, label smoothing.

### 3.2 Evaluation Metrics
- Discrimination: AUC, F1, sensitivity, specificity.
- Calibration: Brier score, ECE, reliability plots.
- Explainability: Grad-CAM IOU (where segmentation available), qualitative review forms.
- Fairness: Stratified performance by skin type, age, sex.
- Uncertainty: Predictive entropy, variance across ensemble members.

### 3.3 Reader Study
- Multi-reader multi-case design with dermatology trainees and experts.
- Each case: image + (optional) metadata + model prediction + Grad-CAM overlay.
- Measure agreement, time-to-decision, confidence ratings.

## 4. Timeline (Indicative)
| Phase | Duration | Activities | Deliverables |
|-------|----------|-----------|-------------|
| Data Prep | Month 1 | Download & clean datasets | Harmonized dataset release |
| Baseline Training | Month 2 | EfficientNet + metadata | Initial benchmark report |
| Advanced Models | Month 3 | ViT/ConvNeXt fusion experiments | Comparative performance matrix |
| Uncertainty & Calibration | Month 4 | Ensemble + calibration tooling | Calibration dashboards |
| Reader Study Setup | Month 5 | IRB submission, protocol finalization | Approved protocol |
| Reader Study Execution | Month 6 | Collect clinician judgments | Annotated study dataset |
| Analysis & Publication | Month 7 | Statistical tests, manuscript | Draft manuscript submission |

## 5. Resources
- Compute: 2× GPUs (>=12GB), storage for raw and preprocessed images (~200GB).
- Personnel: 1 ML engineer, 1 data curator, 2 clinical advisors, 3 reader study participants.
- Tooling: PyTorch, timm, Streamlit, Hugging Face Spaces, calibration/uncertainty libraries.

## 6. Risk & Mitigation
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Data access delays | Slips timeline | Parallel synthetic experiments |
| Class imbalance | Skewed metrics | Use focal loss & resampling |
| Metadata missingness | Reduced fusion gains | Imputation + robust modeling |
| Calibration drift | Unsafe confidence usage | Periodic recalibration |\n| Reader recruitment | Underpowered study | Early invitations + incentives |

## 7. Deliverables
- Harmonized dataset scripts & documentation.
- Baseline and advanced model benchmark tables.
- Calibration & uncertainty evaluation reports.
- Reader study dataset + analysis.
- Manuscript targeting medical AI venue (e.g., MICCAI, JMIR, Nature Digital Medicine).

## 8. Publication Targets
- Short-Term: Workshop paper (interpretability focus).
- Mid-Term: Full conference (multimodal fusion + fairness).
- Long-Term: Journal submission (clinical validation + reader study outcomes).

## 9. Alignment with Regulatory Pathways
- Maintain versioned model cards & performance logs.
- Document bias assessments and monitoring plan (SaMD lifecycle principles).
- Prepare traceability matrix: data lineage, preprocessing, model versions.

## 10. Next Steps
1. Implement real ISIC/HAM10000 loaders.
2. Add ensemble uncertainty branch to training script.
3. Integrate calibration evaluation post-training.
4. Draft IRB protocol for reader study.
5. Begin external dataset partnership outreach.
