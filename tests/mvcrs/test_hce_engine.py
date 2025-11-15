#!/usr/bin/env python3
"""
Tests for MV-CRS Horizon Coherence Engine (Phase XL)

Validates coherence classification, divergence clusters, instability score,
confidence handling, fix-branch simulation, and audit marker idempotency.
"""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone
import pytest

# Path for importing engine
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'scripts' / 'mvcrs'))
import mvcrs_horizon_coherence as hce

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def temp_workspace(tmp_path):
    os.environ['MVCRS_BASE_DIR'] = str(tmp_path)
    (tmp_path / 'state').mkdir(exist_ok=True)
    (tmp_path / 'logs').mkdir(exist_ok=True)
    yield tmp_path
    os.environ.pop('MVCRS_BASE_DIR', None)

# Helpers to create minimal states

def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2))


def make_feedback(ws, status='ok'):
    write_json(ws / 'state' / 'mvcrs_feedback.json', {
        'mvcrs_status': status,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


def make_strategic(ws, health='ok', confidence=0.9):
    write_json(ws / 'state' / 'mvcrs_strategic_influence.json', {
        'mvcrs_health': health,
        'strategic_profile': 'stable',
        'confidence': confidence,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


def make_fusion(ws, state='GREEN'):
    write_json(ws / 'state' / 'policy_fusion_state.json', {
        'fusion_state': state,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


def make_forensic(ws, drift=0.1):
    write_json(ws / 'state' / 'forensic_forecast.json', {
        'drift_probability': drift,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


def make_hlgs(ws, status='stable', instability=0.05):
    write_json(ws / 'state' / 'mvcrs_long_horizon_plan.json', {
        'status': status,
        'predicted_policy_instability': instability,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


def make_adaptive_history(ws, pattern: str):
    path = ws / 'state' / 'adaptive_response_history.jsonl'
    lines = []
    if pattern == 'stable':
        for i in range(5):
            lines.append({'action': 'monitor'})
    elif pattern == 'escalating':
        for i in range(3):
            lines.append({'action': 'escalate_threshold'})
    elif pattern == 'intervening':
        for i in range(3):
            lines.append({'action': 'intervene_lock'})
    elif pattern == 'quiet':
        for i in range(7):
            lines.append({'action': 'monitor_passive'})
    with open(path, 'w', encoding='utf-8') as f:
        for obj in lines:
            f.write(json.dumps(obj) + '\n')

# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_perfect_alignment(temp_workspace):
    make_adaptive_history(temp_workspace, 'stable')
    make_fusion(temp_workspace, 'GREEN')
    make_forensic(temp_workspace, 0.1)
    make_feedback(temp_workspace, 'ok')
    make_strategic(temp_workspace, 'ok', confidence=0.95)
    make_hlgs(temp_workspace, 'stable', 0.05)
    exit_code = hce.run_hce_engine()
    assert exit_code == 0
    data = json.loads((temp_workspace / 'state' / 'mvcrs_horizon_coherence.json').read_text())
    assert data['coherence_status'] == 'aligned'
    assert data['governance_alignment_recommendation'] == 'hold'
    assert data['instability_score'] < 0.4


def test_soft_contradictions_tension(temp_workspace):
    make_adaptive_history(temp_workspace, 'stable')
    make_fusion(temp_workspace, 'YELLOW')
    make_forensic(temp_workspace, 0.35)
    make_feedback(temp_workspace, 'warning')
    make_strategic(temp_workspace, 'warning', confidence=0.8)
    make_hlgs(temp_workspace, 'volatile', 0.4)
    exit_code = hce.run_hce_engine()
    assert exit_code in (0,1)  # tension may return 0
    data = json.loads((temp_workspace / 'state' / 'mvcrs_horizon_coherence.json').read_text())
    assert data['coherence_status'] in ['tension','conflict']
    assert data['instability_score'] >= 0.3
    assert data['governance_alignment_recommendation'] in ['stabilize','intervene']


def test_hard_contradictions_conflict(temp_workspace):
    make_adaptive_history(temp_workspace, 'stable')
    make_fusion(temp_workspace, 'RED')
    make_forensic(temp_workspace, 0.8)
    make_feedback(temp_workspace, 'ok')
    make_strategic(temp_workspace, 'ok', confidence=0.9)
    make_hlgs(temp_workspace, 'critical', 0.85)
    exit_code = hce.run_hce_engine()
    data = json.loads((temp_workspace / 'state' / 'mvcrs_horizon_coherence.json').read_text())
    assert data['coherence_status'] == 'conflict'
    assert 'short_vs_long' in data['conflict_sources'] or 'mid_vs_long' in data['conflict_sources']
    assert data['governance_alignment_recommendation'] == 'intervene'


def test_divergence_cluster_detection(temp_workspace):
    make_adaptive_history(temp_workspace, 'stable')
    make_fusion(temp_workspace, 'RED')
    make_forensic(temp_workspace, 0.7)
    make_feedback(temp_workspace, 'warning')
    make_strategic(temp_workspace, 'warning', confidence=0.7)
    make_hlgs(temp_workspace, 'critical', 0.8)
    exit_code = hce.run_hce_engine()
    data = json.loads((temp_workspace / 'state' / 'mvcrs_horizon_coherence.json').read_text())
    # cluster triggers intervene
    assert data['governance_alignment_recommendation'] == 'intervene'
    assert data['instability_score'] >= 0.5


def test_instability_score_bounds(temp_workspace):
    make_adaptive_history(temp_workspace, 'intervening')
    make_fusion(temp_workspace, 'RED')
    make_forensic(temp_workspace, 0.95)
    make_feedback(temp_workspace, 'failed')
    make_strategic(temp_workspace, 'failed', confidence=0.3)
    make_hlgs(temp_workspace, 'critical', 0.95)
    exit_code = hce.run_hce_engine()
    data = json.loads((temp_workspace / 'state' / 'mvcrs_horizon_coherence.json').read_text())
    assert 0.0 <= data['instability_score'] <= 1.0
    assert data['instability_score'] >= 0.7


def test_confidence_missing_optional(temp_workspace):
    # Only provide mandatory fusion + HLGS, omit forensic + feedback + strategic + adaptive history
    make_fusion(temp_workspace, 'GREEN')
    make_hlgs(temp_workspace, 'stable', 0.05)
    exit_code = hce.run_hce_engine()
    data = json.loads((temp_workspace / 'state' / 'mvcrs_horizon_coherence.json').read_text())
    assert data['confidence'] < 0.6  # reduced due to missing inputs


def test_fix_branch_on_persistent_failure(temp_workspace, monkeypatch):
    make_fusion(temp_workspace, 'GREEN')
    make_hlgs(temp_workspace, 'stable', 0.05)

    def mock_write_state(obj):
        return False
    monkeypatch.setattr(hce, 'write_state', mock_write_state)
    exit_code = hce.run_hce_engine()
    assert exit_code == 2


def test_idempotent_audit_marker(temp_workspace):
    # Prepare summary file
    summary = temp_workspace / 'INSTRUCTION_EXECUTION_SUMMARY.md'
    summary.write_text('# Summary\nInitial content\n')
    make_fusion(temp_workspace, 'GREEN')
    make_hlgs(temp_workspace, 'stable', 0.05)
    hce.run_hce_engine()
    hce.run_hce_engine()
    content = summary.read_text()
    assert content.count('<!-- MVCRS_HCE: UPDATED') == 1

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
