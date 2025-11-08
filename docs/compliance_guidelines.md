# Compliance Guidelines for BioSignal-X

This document summarizes key regulatory references and maps BioSignal-X capabilities to foundational Software as a Medical Device (SaMD) expectations.

## Regulatory References
- FDA SaMD: Clinical Evaluation of SaMD – Key Definitions and Regulatory Expectations.
- EU MDR (2017/745): Requirements for medical devices and software classification.
- ISO 14155: Clinical investigation of medical devices for human subjects — Good clinical practice.
- ISO 13485: Quality management systems for medical devices.
- IMDRF SaMD guidance: Clinical evaluation and risk categorization.

## Capability Mapping
- Traceability & Reproducibility
  - Versioned codebase with Git tags, `CHANGELOG.md`, and `CITATION.cff`.
  - Training/tracking: calibration report (`results/calibration_report.csv`), metrics logs, and notebook benchmarks.
  - Traceability JSON log (`logs/traceability.json`) records model checkpoints, configs, datasets, and timestamps.
- Bias Mitigation & Fairness
  - Benchmark notebook computes fairness across demographics (sex, age bins, skin type if available).
  - Literature and experimental plan emphasize bias audits and calibration.
- Explainability
  - Grad-CAM overlays built-in; roadmap includes Integrated Gradients and DeepLIFT.
- Clinical Validation
  - `clinical_validation/validate_clinical.py` supports external cohort validation with per-case outputs and group summaries.
- Data Protection
  - External dataset ingestion is user-directed; no PHI persisted beyond configured outputs.

## Roadmap toward Compliance
- Documentation: Maintain model cards, data lineage, and risk assessments.
- Prospective Study: Reader study protocol aligned with ISO 14155 principles.
- Post-market Plan: Establish monitoring for drift, bias, and calibration.
- QMS Integration: Align development workflows with ISO 13485 procedures.
