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

## ISO 14971 Risk Management
This section outlines key hazards for AI-assisted dermatology, corresponding mitigations, and residual risk. It is intended as a living risk register.

| Hazard | Harm | Cause | Mitigations (Controls) | Verification | Residual Risk |
|---|---|---|---|---|---|
| Misclassification (FN) | Delayed treatment | Limited generalization; domain shift | Calibration monitoring (ECE/Brier), uncertainty estimates (MC Dropout), human-in-the-loop review | External clinical validation; calibration report; uncertainty analysis | Reduced but present; clinician oversight required |
| Misclassification (FP) | Unnecessary procedures/anxiety | Overconfidence; class imbalance | Threshold tuning; calibration; decision support labels | ROC/PR analysis; calibration bins | Reduced; shared decision-making |
| Demographic bias | Inequitable performance | Under-representation | Fairness audits (ΔAUC/ΔECE), inter-site benchmarking, dataset curation | Group-wise metrics; fairness JSONs | Reduced; monitor and retrain as needed |
| Data drift | Performance degradation | Acquisition/site changes | Weekly drift detection (JSD), alerts and revalidation triggers | Drift report JSON; CI logs | Controlled via monitoring |
| Software defect | Incorrect outputs | Implementation errors | Code review, unit tests, CI, versioning | Tests passing; CHANGELOG | Low with QMS controls |

## IEC 62304 Lifecycle Mapping
Mapping of BioSignal-X workflows to the software lifecycle processes.

- Development: Requirements captured in README/docs; modular PyTorch model; reproducible datasets and preprocessing; versioned releases.
- Verification: Unit tests (placeholder), automated training metrics, calibration and fairness checks, benchmark notebooks.
- Validation: Clinical validation script with per-case and cohort summaries; traceability logs linking model hash and datasets.
- Risk Management (interface to ISO 14971): Ongoing hazard analysis; controls captured above; monitoring via drift detection.
- Maintenance: Issue tracking, CHANGELOG, scheduled drift checks and periodic reviews; revalidation on significant changes.

## Post-Market Surveillance (PMS)
- Drift Detection: Automated weekly job runs `monitoring/drift_detector.py` and stores `results/drift_report.json`.
- Audit Frequency: Quarterly full audit of calibration, fairness, and inter-site metrics; ad-hoc if drift exceeds threshold.
- Revalidation Triggers: Significant drift, dataset shift, model update, or clinical incident; perform clinical validation rerun and update documentation.
- Escalation Path: Open GitHub issue automatically and notify maintainers.

## End-to-End Traceability
- Model Version/Hash: Stored each epoch in `logs/traceability.json`.
- Dataset Lineage: `metadata.csv` plus benchmark artifacts document sources and splits.
- Validation Cohort: `results/clinical_outputs/summary.csv` and `group_summary.csv` record cohort performance.
- Monitoring: `results/drift_report.json` archived with timestamp; links to weekly CI run.
