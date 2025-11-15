#!/usr/bin/env python3
"""Tests for MV-CRS Governance Drift Auditor (Phase XLII)

Covers:
1. Missing history → low confidence, low drift
2. Stubborn governance (expected high risk, observed constant RED, no interventions) → high drift components (stubbornness)
3. Overcorrection pattern (oscillating intervene/monitor) → drift_direction="overcorrection"
4. Volatility cycle detection (frequent policy state transitions) elevates volatility_cycle
5. Contributing factor ranking stability across runs (deterministic ordering)
6. Confidence clamping within [0,1]
7. Write failure → fix branch creation and exit code 2
8. Audit marker idempotency (single marker after multiple runs)
9. Deterministic drift_score for identical inputs (repeatability)

Uses MVCRS_BASE_DIR virtualization for isolation.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.audit.mvcrs_governance_drift_auditor import (
    build_governance_drift,
    run_gda_engine,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def write_json(base: Path, rel: str, obj):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f)


def write_jsonl(base: Path, rel: str, rows):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')


def iso_now():
    return datetime.now(timezone.utc).isoformat()

# ------------------------------------------------------------------
# Test Cases
# ------------------------------------------------------------------

class TestGovernanceDriftAuditor(unittest.TestCase):

    def test_missing_history_low_confidence_low_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Only minimal MHPE snapshot
            write_json(base, 'state/mvcrs_multi_horizon_ensemble.json', {
                'instability_1d': 0.12,
                'instability_7d': 0.15,
                'instability_30d': 0.18,
                'timestamp': iso_now()
            })
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                drift = build_governance_drift()
            self.assertLess(drift['drift_score'], 0.35, 'Drift should be low with minimal calm data')
            self.assertLess(drift['confidence'], 0.5, 'Confidence should be low with missing sources')

    def test_stubborn_governance_high_drift_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Expected high risk series (synthetic)
            write_json(base, 'state/mvcrs_multi_horizon_ensemble.json', {
                'synthetic_expected_series': [0.8]*90,
                'timestamp': iso_now()
            })
            # Observed constant RED states, no interventions
            fusion_log_rows = [{'fusion_state': 'RED', 'timestamp': iso_now()} for _ in range(30)]
            write_jsonl(base, 'logs/policy_fusion_state_log.jsonl', fusion_log_rows)
            # Empty adaptive history -> no interventions
            write_jsonl(base, 'state/adaptive_response_history.jsonl', [])
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                drift = build_governance_drift()
            self.assertGreaterEqual(drift['components']['stubbornness'], 0.6,
                                     'Stubbornness should be elevated for constant RED with high expected risk and no interventions')
            self.assertIn('stubbornness', drift['contributing_factors'][0], 'Stubbornness should appear as leading factor')

    def test_overcorrection_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_json(base, 'state/mvcrs_multi_horizon_ensemble.json', {
                'synthetic_expected_series': [0.5]*90,
                'timestamp': iso_now()
            })
            # Moderate observed states
            fusion_log_rows = []
            for i in range(20):
                fusion_log_rows.append({'fusion_state': 'YELLOW', 'timestamp': iso_now()})
            write_jsonl(base, 'logs/policy_fusion_state_log.jsonl', fusion_log_rows)
            # Adaptive oscillating intervene/monitor pattern
            adaptive_rows = []
            for i in range(15):
                adaptive_rows.append({'action': 'intervene' if i % 2 == 0 else 'monitor', 'timestamp': iso_now()})
            write_jsonl(base, 'state/adaptive_response_history.jsonl', adaptive_rows)
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                drift = build_governance_drift()
            self.assertEqual(drift['drift_direction'], 'overcorrection', 'Direction should be overcorrection for oscillating actions')
            self.assertGreater(drift['components']['overcorrection'], 0.2, 'Overcorrection component should be non-trivial')

    def test_volatility_cycle_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_json(base, 'state/mvcrs_multi_horizon_ensemble.json', {
                'synthetic_expected_series': [0.4]*90,
                'timestamp': iso_now()
            })
            # Rapid transitions between states
            states = ['GREEN','YELLOW','RED','YELLOW','GREEN'] * 6
            fusion_log_rows = [{'fusion_state': s, 'timestamp': iso_now()} for s in states]
            write_jsonl(base, 'logs/policy_fusion_state_log.jsonl', fusion_log_rows)
            write_jsonl(base, 'state/adaptive_response_history.jsonl', [])
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                drift = build_governance_drift()
            self.assertGreater(drift['components']['volatility_cycle'], 0.3, 'Volatility cycle should reflect frequent transitions')
            self.assertIn('volatility', ' '.join(drift['contributing_factors']))

    def test_contributing_factors_stability(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_json(base, 'state/mvcrs_multi_horizon_ensemble.json', {
                'synthetic_expected_series': [0.55]*90,
                'timestamp': iso_now()
            })
            # Mild transitions
            fusion_log_rows = [{'fusion_state': 'YELLOW', 'timestamp': iso_now()} for _ in range(25)]
            write_jsonl(base, 'logs/policy_fusion_state_log.jsonl', fusion_log_rows)
            write_jsonl(base, 'state/adaptive_response_history.jsonl', [{'action':'monitor','timestamp':iso_now()}])
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                drift1 = build_governance_drift()
                drift2 = build_governance_drift()
            self.assertEqual(drift1['contributing_factors'], drift2['contributing_factors'], 'Factors ordering must be deterministic')
            self.assertEqual(drift1['drift_score'], drift2['drift_score'], 'Drift score must be deterministic')

    def test_confidence_clamping(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            # Provide empty sources to reduce availability
            write_json(base, 'state/mvcrs_multi_horizon_ensemble.json', {
                'synthetic_expected_series': [0.2]*90,
                'timestamp': iso_now()
            })
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                drift = build_governance_drift()
            self.assertGreaterEqual(drift['confidence'], 0.0, 'Confidence lower bound')
            self.assertLessEqual(drift['confidence'], 1.0, 'Confidence upper bound')

    def test_write_failure_creates_fix_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_json(base, 'state/mvcrs_multi_horizon_ensemble.json', {
                'synthetic_expected_series': [0.3]*90,
                'timestamp': iso_now()
            })
            summary_path = base / 'INSTRUCTION_EXECUTION_SUMMARY.md'
            summary_path.write_text('# Summary\n', encoding='utf-8')
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                with patch('scripts.audit.mvcrs_governance_drift_auditor.atomic_write', return_value=False):
                    with patch('scripts.audit.mvcrs_governance_drift_auditor.append_log', return_value=False):
                        with patch('scripts.audit.mvcrs_governance_drift_auditor.create_fix_branch') as mock_branch:
                            exit_code = run_gda_engine()
            self.assertEqual(exit_code, 2, 'Exit code 2 expected on persistent failure')
            mock_branch.assert_called_once()

    def test_audit_marker_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            summary_path = base / 'INSTRUCTION_EXECUTION_SUMMARY.md'
            summary_path.write_text('# Summary\nInitial\n', encoding='utf-8')
            write_json(base, 'state/mvcrs_multi_horizon_ensemble.json', {
                'synthetic_expected_series': [0.25]*90,
                'timestamp': iso_now()
            })
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                for _ in range(3):
                    run_gda_engine()
            content = summary_path.read_text(encoding='utf-8')
            markers = [ln for ln in content.split('\n') if ln.startswith('<!-- MVCRS_GDA:')]
            self.assertEqual(len(markers), 1, 'Exactly one GDA marker expected after multiple runs')

    def test_drift_score_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_json(base, 'state/mvcrs_multi_horizon_ensemble.json', {
                'synthetic_expected_series': [0.6]*90,
                'timestamp': iso_now()
            })
            states = ['YELLOW']*30
            fusion_log_rows = [{'fusion_state': s, 'timestamp': iso_now()} for s in states]
            write_jsonl(base, 'logs/policy_fusion_state_log.jsonl', fusion_log_rows)
            write_jsonl(base, 'state/adaptive_response_history.jsonl', [{'action':'monitor','timestamp':iso_now()}])
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                scores = [build_governance_drift()['drift_score'] for _ in range(5)]
            self.assertEqual(len(set(scores)), 1, 'Drift score must be consistent across repeated runs')

if __name__ == '__main__':
    unittest.main()
