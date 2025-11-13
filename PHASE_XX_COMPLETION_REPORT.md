# Phase XX Completion Report — Federated Reputation & Weighted Consensus

Date: 2025-11-14T00:00:00Z

Scope:
- Reputation Index Engine to score peers using recent agreement history, drift stability, and ethics fairness
- Weighted Consensus Engine to compute weighted agreement and confidence interval
- Portal update with Federated Confidence meter (weighted agreement and top trusted peers)
- Weekly workflows for index generation and verification
- Regression tests for reputation scoring and weighted consensus aggregation

Scripts:
- scripts/federation/reputation_index_engine.py — computes agreement_score, stability_penalty, ethics_bonus; writes federation/reputation_index.json; appends REPUTATION_INDEX marker
- scripts/federation/weighted_consensus_engine.py — recomputes weighted consensus from peer hashes and reputation scores; writes federation/weighted_consensus.json; appends WEIGHTED_CONSENSUS marker

Tests:
- tests/federation/test_reputation_index.py — validates scoring math, clamping, and expected ordering
- tests/federation/test_weighted_consensus.py — validates weighted majority behavior and audit marker

Workflows:
- .github/workflows/reputation_index.yml — Thursdays 05:00 UTC; uploads reputation_index.json
- .github/workflows/weighted_consensus_verification.yml — Fridays 05:30 UTC; runs tests and uploads JUnit

Portal:
- portal/index.html — Federated Confidence card displaying weighted agreement, 95% CI, and top 3 trusted peers

Outcome:
Peers are no longer equal by default—reputation drives influence on consensus. Weighted agreement and confidence provide clearer governance signals, surfaced live in the portal.

Tag:
v2.4.0-reputation
