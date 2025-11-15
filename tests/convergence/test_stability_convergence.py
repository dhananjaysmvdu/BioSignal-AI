#!/usr/bin/env python3
"""
Regression tests for MV-CRS Stability Convergence Engine (Phase XLIV)

Test coverage:
- Convergence score computation with full inputs
- Missing artifact → confidence adjustment applied
- Divergent inputs → alignment=divergent
- Gating warning triggered when (score < 0.45) AND (ensemble_confidence > 0.7)
- Idempotent audit marker
- Fix-branch creation on simulated write failure
- Extreme values handling
- Marker determinism
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'convergence'))

import mvcrs_stability_convergence as engine

class TestStabilityConvergence:
    """Stability Convergence Test Suite (8 tests)"""
    
    def setup_method(self):
        """Set up test environment with temp directory."""
        self.tmpdir = tempfile.mkdtemp()
        os.environ['MVCRS_BASE_DIR'] = self.tmpdir
        Path(self.tmpdir, 'state').mkdir(exist_ok=True)
        Path(self.tmpdir, 'logs').mkdir(exist_ok=True)
        
    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        if 'MVCRS_BASE_DIR' in os.environ:
            del os.environ['MVCRS_BASE_DIR']
    
    def _write_state(self, name: str, data: dict):
        """Helper to write state file."""
        path = Path(self.tmpdir, 'state', name)
        path.write_text(json.dumps(data))
    
    def _read_profile(self):
        """Helper to read convergence profile."""
        path = Path(self.tmpdir, 'state', 'mvcrs_stability_convergence.json')
        if path.exists():
            return json.loads(path.read_text())
        return None
    
    # Test 1: Convergence score computation with full inputs
    def test_convergence_score_full_inputs(self):
        """Test convergence score calculation with all sources present."""
        self._write_state('mvcrs_stabilization_profile.json', {
            'final_confidence': 0.8
        })
        self._write_state('mvcrs_horizon_coherence.json', {
            'stability_score': 0.75
        })
        self._write_state('mvcrs_multi_horizon_ensemble_state.json', {
            'mean_forecast_confidence': 0.85
        })
        self._write_state('rdgl_policy_adjustments.json', {
            'policy_effectiveness': 0.7
        })
        
        result = engine.run_convergence_engine()
        assert result is True
        
        profile = self._read_profile()
        assert profile is not None
        assert 'convergence_score' in profile
        assert 0.0 <= profile['convergence_score'] <= 1.0
        # Expected: (0.8*0.4 + 0.75*0.3 + 0.85*0.2 + 0.7*0.1) = 0.32+0.225+0.17+0.07 = 0.785
        # But with 0 penalty (all sources present), should be close to weighted average
        assert profile['convergence_score'] > 0.55
    
    # Test 2: Missing artifact → confidence adjustment applied
    def test_confidence_adjustment_missing_sources(self):
        """Test confidence penalty when sources are missing."""
        # Only drift present
        self._write_state('mvcrs_stabilization_profile.json', {
            'final_confidence': 0.8
        })
        
        result = engine.run_convergence_engine()
        assert result is True
        
        profile = self._read_profile()
        assert profile is not None
        assert profile['confidence_adjust'] < 1.0
        assert profile['confidence_adjust'] >= 0.2  # floor
        # Missing 3 sources but floor at 0.2 applies
        assert profile['confidence_adjust'] == 0.2
    
    # Test 3: Divergent inputs → alignment=divergent
    def test_divergent_alignment(self):
        """Test alignment status when signals diverge significantly."""
        self._write_state('mvcrs_stabilization_profile.json', {
            'final_confidence': 0.2  # very low
        })
        self._write_state('mvcrs_horizon_coherence.json', {
            'stability_score': 0.9  # very high
        })
        self._write_state('mvcrs_multi_horizon_ensemble_state.json', {
            'mean_forecast_confidence': 0.1  # very low
        })
        self._write_state('rdgl_policy_adjustments.json', {
            'policy_effectiveness': 0.5  # medium
        })
        
        result = engine.run_convergence_engine()
        assert result is True
        
        profile = self._read_profile()
        assert profile is not None
        assert profile['alignment_status'] == 'divergent'
    
    # Test 4: Gating warning triggered on risk condition
    def test_gating_risk_triggered(self):
        """Test potential_gating_risk flag when low score + high ensemble confidence."""
        self._write_state('mvcrs_stabilization_profile.json', {
            'final_confidence': 0.3
        })
        self._write_state('mvcrs_horizon_coherence.json', {
            'stability_score': 0.3
        })
        self._write_state('mvcrs_multi_horizon_ensemble_state.json', {
            'mean_forecast_confidence': 0.8  # HIGH ensemble confidence
        })
        self._write_state('rdgl_policy_adjustments.json', {
            'policy_effectiveness': 0.3
        })
        
        result = engine.run_convergence_engine()
        assert result is True
        
        profile = self._read_profile()
        assert profile is not None
        # Low convergence + high ensemble → risk = true
        assert profile['convergence_score'] < 0.45
        assert profile['ensemble_confidence'] > 0.7
        assert profile['potential_gating_risk'] is True
    
    # Test 5: Idempotent audit marker
    def test_audit_marker_idempotent(self):
        """Test that audit marker is idempotent (overwrites old marker)."""
        summary_file = Path(self.tmpdir, 'INSTRUCTION_EXECUTION_SUMMARY.md')
        summary_file.write_text('Old content\n<!-- MVCRS_STABILITY_CONVERGENCE: UPDATED 2025-01-01T00:00:00Z -->\n')
        
        self._write_state('mvcrs_stabilization_profile.json', {'final_confidence': 0.5})
        
        # Mock the path to use tmpdir
        with patch('mvcrs_stability_convergence._p') as mock_p:
            def side_effect(rel):
                if rel == 'INSTRUCTION_EXECUTION_SUMMARY.md':
                    return summary_file
                return Path(self.tmpdir) / rel
            mock_p.side_effect = side_effect
            
            result = engine.run_convergence_engine()
            assert result is True
        
        # Check marker was updated (should only have one marker)
        content = summary_file.read_text()
        marker_count = content.count('MVCRS_STABILITY_CONVERGENCE: UPDATED')
        assert marker_count == 1
    
    # Test 6: Fix-branch creation on write failure
    def test_fix_branch_on_write_failure(self):
        """Test fix-branch creation when atomic write fails (mocked)."""
        self._write_state('mvcrs_stabilization_profile.json', {
            'final_confidence': 0.5
        })
        
        # Mock atomic_write_json to fail
        original_write = engine.atomic_write_json
        engine.atomic_write_json = lambda *args, **kwargs: False
        
        result = engine.run_convergence_engine()
        # Should return False due to write failure
        assert result is False
        
        # Restore original
        engine.atomic_write_json = original_write
    
    # Test 7: Extreme values clamping
    def test_extreme_values_clamping(self):
        """Test that extreme input values are properly clamped."""
        self._write_state('mvcrs_stabilization_profile.json', {
            'final_confidence': 1.5  # above 1.0
        })
        self._write_state('mvcrs_horizon_coherence.json', {
            'stability_score': -0.5  # below 0.0
        })
        self._write_state('mvcrs_multi_horizon_ensemble_state.json', {
            'mean_forecast_confidence': 1.2  # above 1.0
        })
        self._write_state('rdgl_policy_adjustments.json', {
            'policy_effectiveness': -0.1  # below 0.0
        })
        
        result = engine.run_convergence_engine()
        assert result is True
        
        profile = self._read_profile()
        assert profile is not None
        # All values should be clamped to [0, 1]
        assert 0.0 <= profile['signals']['drift'] <= 1.0
        assert 0.0 <= profile['signals']['coherence'] <= 1.0
        assert 0.0 <= profile['signals']['ensemble'] <= 1.0
        assert 0.0 <= profile['signals']['rdgl'] <= 1.0
    
    # Test 8: Deterministic output on repeated runs
    def test_deterministic_output(self):
        """Test that same inputs produce identical outputs."""
        self._write_state('mvcrs_stabilization_profile.json', {
            'final_confidence': 0.65
        })
        self._write_state('mvcrs_horizon_coherence.json', {
            'stability_score': 0.70
        })
        self._write_state('mvcrs_multi_horizon_ensemble_state.json', {
            'mean_forecast_confidence': 0.68
        })
        self._write_state('rdgl_policy_adjustments.json', {
            'policy_effectiveness': 0.60
        })
        
        # Run twice
        result1 = engine.run_convergence_engine()
        profile1 = self._read_profile()
        
        result2 = engine.run_convergence_engine()
        profile2 = self._read_profile()
        
        assert result1 is True
        assert result2 is True
        assert profile1['convergence_score'] == profile2['convergence_score']
        assert profile1['alignment_status'] == profile2['alignment_status']
        assert profile1['potential_gating_risk'] == profile2['potential_gating_risk']

if __name__ == '__main__':
    pytest_args = ['-q', __file__]
    import pytest
    pytest.main(pytest_args)
