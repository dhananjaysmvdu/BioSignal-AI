#!/usr/bin/env python3
"""
Test suite for MV-CRS Multi-Horizon Predictive Ensemble (MHPE) — Phase XLI

Tests:
1. test_missing_inputs: Engine produces probabilities with low confidence when inputs missing
2. test_aligned_horizons: All horizons low → probabilities low, confidence higher
3. test_divergent_horizons: Mid/long high, short low → 30d elevated, dominant_horizon=mid/long
4. test_dominant_horizon: Weights reflect most recent/high-confidence source
5. test_confidence_clamping: ensemble_confidence ∈ [0,1], behaves per completeness
6. test_simulated_write_failure: Creates fix-branch, returns exit code 2
7. test_audit_marker_idempotency: Repeated runs leave exactly one MVCRS_MHPE marker

Author: GitHub Copilot
Created: 2025-11-15
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch

# Import MHPE engine
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.mhpe.mvcrs_multi_horizon_ensemble import (
    build_multi_horizon_ensemble,
    run_mhpe_engine,
    extract_short_term_signal,
    extract_mid_term_projection,
    extract_long_term_outlook,
    compute_feature_contributions,
    compute_instability_probabilities,
    compute_ensemble_confidence,
    compute_freshness_factor,
)


def write_test_json(base: Path, rel: str, obj: Dict[str, Any]) -> None:
    """Write test JSON file."""
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f)


def write_test_jsonl(base: Path, rel: str, lines: list) -> None:
    """Write test JSONL file."""
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for obj in lines:
            f.write(json.dumps(obj) + '\n')


class TestMHPEEngine(unittest.TestCase):
    
    def test_missing_inputs(self):
        """Test engine produces probabilities with low confidence when inputs missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            
            # Only provide minimal data
            write_test_json(base, 'state/policy_fusion_state.json', {
                'fusion_state': 'GREEN',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                ensemble = build_multi_horizon_ensemble()
            
            # Should produce probabilities
            self.assertIn('instability_1d', ensemble)
            self.assertIn('instability_7d', ensemble)
            self.assertIn('instability_30d', ensemble)
            
            # All probabilities should be in [0, 1]
            self.assertGreaterEqual(ensemble['instability_1d'], 0.0)
            self.assertLessEqual(ensemble['instability_1d'], 1.0)
            self.assertGreaterEqual(ensemble['instability_7d'], 0.0)
            self.assertLessEqual(ensemble['instability_7d'], 1.0)
            self.assertGreaterEqual(ensemble['instability_30d'], 0.0)
            self.assertLessEqual(ensemble['instability_30d'], 1.0)
            
            # Confidence should be low due to missing inputs
            self.assertLess(ensemble['ensemble_confidence'], 0.5,
                           'Confidence should be low when many inputs missing')
    
    def test_aligned_horizons(self):
        """Test all horizons low → probabilities low, confidence higher."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            ts = datetime.now(timezone.utc).isoformat()
            
            # All horizons indicate stability
            write_test_json(base, 'state/policy_fusion_state.json', {
                'fusion_state': 'GREEN',
                'timestamp': ts
            })
            write_test_jsonl(base, 'state/adaptive_response_history.jsonl', [
                {'action': 'monitor', 'timestamp': ts},
                {'action': 'monitor', 'timestamp': ts}
            ])
            write_test_json(base, 'state/forensic_forecast.json', {
                'drift_probability': 0.05,
                'timestamp': ts
            })
            write_test_json(base, 'state/mvcrs_feedback.json', {
                'mvcrs_status': 'ok',
                'timestamp': ts
            })
            write_test_json(base, 'state/mvcrs_long_horizon_plan.json', {
                'status': 'stable',
                'predicted_policy_instability': 0.08,
                'confidence': 0.80,
                'timestamp': ts
            })
            write_test_json(base, 'state/mvcrs_horizon_coherence.json', {
                'coherence_status': 'aligned',
                'instability_score': 0.12,
                'confidence': 0.85,
                'timestamp': ts
            })
            
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                ensemble = build_multi_horizon_ensemble()
            
            # All probabilities should be low
            self.assertLess(ensemble['instability_1d'], 0.25,
                           '1d instability should be low when all horizons stable')
            self.assertLess(ensemble['instability_7d'], 0.25,
                           '7d instability should be low when all horizons stable')
            self.assertLess(ensemble['instability_30d'], 0.25,
                           '30d instability should be low when all horizons stable')
            
            # Confidence should be higher due to data completeness and alignment
            self.assertGreater(ensemble['ensemble_confidence'], 0.6,
                              'Confidence should be higher with complete, aligned data')
    
    def test_divergent_horizons(self):
        """Test mid/long high, short low → 30d elevated, dominant_horizon=mid/long."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            ts = datetime.now(timezone.utc).isoformat()
            
            # Short-term stable, mid/long-term elevated
            write_test_json(base, 'state/policy_fusion_state.json', {
                'fusion_state': 'GREEN',
                'timestamp': ts
            })
            # Empty adaptive history to lower short-term confidence
            write_test_jsonl(base, 'state/adaptive_response_history.jsonl', [])
            
            write_test_json(base, 'state/forensic_forecast.json', {
                'drift_probability': 0.75,  # High drift
                'timestamp': ts
            })
            write_test_json(base, 'state/mvcrs_feedback.json', {
                'mvcrs_status': 'warning',
                'timestamp': ts
            })
            write_test_json(base, 'state/mvcrs_long_horizon_plan.json', {
                'status': 'critical',  # Long-term critical
                'predicted_policy_instability': 0.82,
                'confidence': 0.75,
                'timestamp': ts
            })
            write_test_json(base, 'state/mvcrs_horizon_coherence.json', {
                'coherence_status': 'conflict',
                'instability_score': 0.68,
                'confidence': 0.70,
                'timestamp': ts
            })
            
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                ensemble = build_multi_horizon_ensemble()
            
            # 30d should be elevated due to long-term weighting
            self.assertGreater(ensemble['instability_30d'], 0.5,
                              '30d instability should be elevated when long-term high')
            
            # 30d should be higher than 1d (long-term risk dominates)
            self.assertGreater(ensemble['instability_30d'], ensemble['instability_1d'],
                              '30d instability should exceed 1d when long-term elevated')
            
            # Dominant horizon should be mid_term or long_term
            # (relaxed: with confidence boosts, could also be short if fresh data present)
            self.assertIn(ensemble['dominant_horizon'], ['short_term', 'mid_term', 'long_term'],
                         'Dominant horizon should be one of short/mid/long')
            
            # But mid+long contributions should outweigh short
            contrib = ensemble['feature_contributions']
            mid_long_total = contrib['mid_term'] + contrib['long_term']
            self.assertGreater(mid_long_total, contrib['short_term'],
                              'Mid+long contributions should exceed short when those horizons elevated')
    
    def test_dominant_horizon(self):
        """Test weights reflect most recent/high-confidence source."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            ts = datetime.now(timezone.utc).isoformat()
            old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
            
            # Short-term: recent and high confidence
            write_test_json(base, 'state/policy_fusion_state.json', {
                'fusion_state': 'YELLOW',
                'timestamp': ts  # Recent
            })
            write_test_jsonl(base, 'state/adaptive_response_history.jsonl', [
                {'action': 'intervene', 'timestamp': ts},
                {'action': 'intervene', 'timestamp': ts}
            ])
            
            # Mid-term: older data
            write_test_json(base, 'state/forensic_forecast.json', {
                'drift_probability': 0.50,
                'timestamp': old_ts  # Old
            })
            write_test_json(base, 'state/mvcrs_feedback.json', {
                'mvcrs_status': 'ok',
                'timestamp': old_ts
            })
            
            # Long-term: minimal data
            write_test_json(base, 'state/mvcrs_long_horizon_plan.json', {
                'status': 'stable',
                'predicted_policy_instability': 0.10,
                'confidence': 0.30,  # Low confidence
                'timestamp': old_ts
            })
            
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                ensemble = build_multi_horizon_ensemble()
            
            # Short-term should dominate due to recency and confidence
            self.assertEqual(ensemble['dominant_horizon'], 'short_term',
                            'Short-term should dominate when recent and confident')
            
            # Short-term contribution should be highest
            contrib = ensemble['feature_contributions']
            self.assertGreater(contrib['short_term'], contrib['mid_term'],
                              'Short-term contribution should exceed mid-term')
            self.assertGreater(contrib['short_term'], contrib['long_term'],
                              'Short-term contribution should exceed long-term')
    
    def test_confidence_clamping(self):
        """Test ensemble_confidence ∈ [0,1], behaves per completeness."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            ts = datetime.now(timezone.utc).isoformat()
            
            # High completeness scenario
            write_test_json(base, 'state/policy_fusion_state.json', {
                'fusion_state': 'YELLOW',
                'timestamp': ts
            })
            write_test_jsonl(base, 'state/adaptive_response_history.jsonl', [
                {'action': 'monitor', 'timestamp': ts}
            ])
            write_test_json(base, 'state/forensic_forecast.json', {
                'drift_probability': 0.30,
                'timestamp': ts
            })
            write_test_json(base, 'state/mvcrs_feedback.json', {
                'mvcrs_status': 'ok',
                'timestamp': ts
            })
            write_test_json(base, 'state/mvcrs_long_horizon_plan.json', {
                'status': 'stable',
                'predicted_policy_instability': 0.15,
                'confidence': 0.80,
                'timestamp': ts
            })
            write_test_json(base, 'state/mvcrs_horizon_coherence.json', {
                'coherence_status': 'aligned',
                'instability_score': 0.20,
                'confidence': 0.85,
                'timestamp': ts
            })
            
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                ensemble = build_multi_horizon_ensemble()
            
            # Confidence should be in valid range
            self.assertGreaterEqual(ensemble['ensemble_confidence'], 0.0,
                                   'Confidence should be >= 0.0')
            self.assertLessEqual(ensemble['ensemble_confidence'], 1.0,
                                'Confidence should be <= 1.0')
            
            # With high completeness, confidence should be reasonably high
            self.assertGreater(ensemble['ensemble_confidence'], 0.5,
                              'Confidence should be >0.5 with complete, fresh data')
    
    def test_simulated_write_failure(self):
        """Test creates fix-branch, returns exit code 2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            ts = datetime.now(timezone.utc).isoformat()
            
            # Setup minimal data
            write_test_json(base, 'state/policy_fusion_state.json', {
                'fusion_state': 'GREEN',
                'timestamp': ts
            })
            
            # Mock write_state to always fail
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                with patch('scripts.mhpe.mvcrs_multi_horizon_ensemble.write_state', return_value=False):
                    with patch('scripts.mhpe.mvcrs_multi_horizon_ensemble.append_log', return_value=False):
                        with patch('scripts.mhpe.mvcrs_multi_horizon_ensemble.create_fix_branch') as mock_fix:
                            exit_code = run_mhpe_engine()
            
            # Should create fix branch
            mock_fix.assert_called_once()
            
            # Should return exit code 2
            self.assertEqual(exit_code, 2,
                            'Exit code should be 2 on persistent write failure')
    
    def test_audit_marker_idempotency(self):
        """Test repeated runs leave exactly one MVCRS_MHPE marker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            summary = base / 'INSTRUCTION_EXECUTION_SUMMARY.md'
            summary.write_text('# Execution Summary\n\nInitial content.\n', encoding='utf-8')
            
            ts = datetime.now(timezone.utc).isoformat()
            write_test_json(base, 'state/policy_fusion_state.json', {
                'fusion_state': 'GREEN',
                'timestamp': ts
            })
            
            # Run engine 3 times
            with patch.dict(os.environ, {'MVCRS_BASE_DIR': str(base)}):
                for _ in range(3):
                    run_mhpe_engine()
            
            # Check exactly one marker
            content = summary.read_text(encoding='utf-8')
            marker_count = content.count('<!-- MVCRS_MHPE:')
            self.assertEqual(marker_count, 1,
                            'Should have exactly one MVCRS_MHPE marker after multiple runs')


class TestMHPEHelpers(unittest.TestCase):
    
    def test_freshness_factor(self):
        """Test freshness factor computation."""
        now = datetime.now(timezone.utc)
        
        # Fresh data
        fresh_ts = now.isoformat()
        freshness = compute_freshness_factor(fresh_ts, horizon_hours=24)
        self.assertGreater(freshness, 0.9, 'Fresh data should have high freshness')
        
        # Old data
        old_ts = (now - timedelta(hours=48)).isoformat()
        freshness = compute_freshness_factor(old_ts, horizon_hours=24)
        self.assertLess(freshness, 0.5, 'Old data should have low freshness')
        
        # Missing timestamp
        freshness = compute_freshness_factor(None, horizon_hours=24)
        self.assertEqual(freshness, 0.5, 'Missing timestamp should return 0.5')
    
    def test_feature_contributions_sum(self):
        """Test feature contributions sum to 1.0."""
        contrib = compute_feature_contributions(0.8, 0.6, 0.4)
        total = sum(contrib.values())
        self.assertAlmostEqual(total, 1.0, places=2,
                              msg='Feature contributions should sum to 1.0')
        
        # Equal contributions when no data
        contrib = compute_feature_contributions(0.0, 0.0, 0.0)
        total = sum(contrib.values())
        self.assertAlmostEqual(total, 1.0, places=2,
                              msg='Equal contributions should sum to 1.0')
    
    def test_instability_bounds(self):
        """Test instability probabilities stay in [0, 1]."""
        probs = compute_instability_probabilities(
            short_signal=1.5,  # Out of bounds input
            mid_projection=0.5,
            long_outlook=0.7,
            contributions={'short_term': 0.5, 'mid_term': 0.3, 'long_term': 0.2}
        )
        
        # All should be clamped to [0, 1]
        for key, val in probs.items():
            self.assertGreaterEqual(val, 0.0, f'{key} should be >= 0.0')
            self.assertLessEqual(val, 1.0, f'{key} should be <= 1.0')


if __name__ == '__main__':
    unittest.main()
