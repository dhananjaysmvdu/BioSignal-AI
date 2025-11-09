# Reviewers Guide: Adaptive Governance Reviews

This guide helps human reviewers consistently validate policy adjustments.

## Decision taxonomy
- Approved: Policy remains as tuned.
- Revised: Propose changes (e.g., drift thresholds, audit depth).
- Rejected: Policy is unsafe or unjustified; specify required changes.

## What to check
- Forecast: Drift probability, expected remediations, confidence.
- Audit health: Pass/fail counts, recent anomalies, remediation actions.
- Governance policy: Current audit depth and drift threshold.
- Ethical context: Potential biases, fairness impacts, safety/security risks.

## Rationale quality
- Reference specific metrics (numbers, dates).
- Explain why the threshold/depth is sufficient (or not).
- Note any uncertainty or data quality concerns.
- Be concise but actionable.

## Where to find artifacts
- Forecast: `reports/provenance_forecast.json`
- Policy: `configs/governance_policy.json`
- Latest audit summary: `reports/audit_summary.md`
- Dashboard: `reports/provenance_dashboard.html`
- Review template (to fill): `reports/reviews/pending/review_<decision_id>.md`

## Submitting the review
- Fill the template fields (Reviewer, Verdict, Rationale, Timestamp).
- Move the completed file to `reports/reviews/completed/`.
- Commit the change; the ledger job will record it automatically.
