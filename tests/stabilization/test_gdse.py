import os, shutil, json, tempfile, sys
from pathlib import Path
import importlib.util

ENGINE_PATH = Path(__file__).resolve().parent.parent.parent / 'scripts' / 'stabilization' / 'mvcrs_governance_drift_stabilizer.py'

spec = importlib.util.spec_from_file_location('gdse_engine', ENGINE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Helper to set up isolated MVCRS base dir

def make_env():
    tmp = Path(tempfile.mkdtemp())
    os.environ['MVCRS_BASE_DIR'] = str(tmp)
    (tmp/'state').mkdir(parents=True, exist_ok=True)
    (tmp/'logs').mkdir(parents=True, exist_ok=True)
    return tmp


def write_json(base: Path, rel: str, obj):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p,'w',encoding='utf-8') as f:
        json.dump(obj,f)
    return p


def test_high_drift_high_stress_intensity_high():
    base = make_env()
    write_json(base,'state/mvcrs_governance_drift.json', {'drift_score':0.9})
    write_json(base,'state/mvcrs_horizon_coherence.json', {'instability_score':0.8})
    write_json(base,'state/mvcrs_multi_horizon_ensemble.json', {'instability_7d':0.7})
    profile = mod.build_stabilization_profile()
    assert profile['stabilization_intensity'] == 'high'


def test_low_drift_low_stress_intensity_low():
    base = make_env()
    write_json(base,'state/mvcrs_governance_drift.json', {'drift_score':0.1})
    write_json(base,'state/mvcrs_horizon_coherence.json', {'instability_score':0.15})
    write_json(base,'state/mvcrs_multi_horizon_ensemble.json', {'instability_7d':0.2})
    profile = mod.build_stabilization_profile()
    assert profile['stabilization_intensity'] == 'low'


def test_confidence_fallback_to_moderate():
    base = make_env()
    # low recency (no log) creates recency=0 -> confidence=0 -> fallback moderate
    write_json(base,'state/mvcrs_governance_drift.json', {'drift_score':0.9})
    write_json(base,'state/mvcrs_horizon_coherence.json', {'instability_score':0.9})
    write_json(base,'state/mvcrs_multi_horizon_ensemble.json', {'instability_7d':0.9})
    profile = mod.build_stabilization_profile()
    assert profile['final_confidence'] < 0.3
    assert profile['stabilization_intensity'] == 'moderate'


def test_threshold_shift_pct_clamped():
    base = make_env()
    write_json(base,'state/mvcrs_governance_drift.json', {'drift_score':1.0})
    write_json(base,'state/mvcrs_horizon_coherence.json', {'instability_score':0.0})
    write_json(base,'state/mvcrs_multi_horizon_ensemble.json', {'instability_7d':0.5})
    profile = mod.build_stabilization_profile()
    assert -2.0 <= profile['correction_vector']['threshold_shift_pct'] <= 2.0


def test_rdgl_learning_rate_factor_clamped():
    base = make_env()
    write_json(base,'state/mvcrs_governance_drift.json', {'drift_score':0.0})
    write_json(base,'state/mvcrs_horizon_coherence.json', {'instability_score':1.0})
    write_json(base,'state/mvcrs_multi_horizon_ensemble.json', {'instability_7d':0.5})
    profile = mod.build_stabilization_profile()
    v = profile['correction_vector']['rdgl_learning_rate_factor']
    assert 0.7 <= v <= 1.3


def test_write_failure_triggers_fix_branch(monkeypatch):
    base = make_env()
    write_json(base,'state/mvcrs_governance_drift.json', {'drift_score':0.6})
    write_json(base,'state/mvcrs_horizon_coherence.json', {'instability_score':0.6})
    write_json(base,'state/mvcrs_multi_horizon_ensemble.json', {'instability_7d':0.6})
    summary = base/'INSTRUCTION_EXECUTION_SUMMARY.md'
    summary.write_text('# Summary\n', encoding='utf-8')
    def fail_atomic(*a, **k):
        return False
    def fail_log(*a, **k):
        return False
    monkeypatch.setattr(mod, 'atomic_write', fail_atomic)
    monkeypatch.setattr(mod, 'append_log', fail_log)
    rc = mod.run_gdse_engine()
    content = summary.read_text(encoding='utf-8')
    assert rc == 2
    assert 'MVCRS_GDSE:' in content and 'FAILED' in content


def test_audit_marker_idempotency():
    base = make_env()
    write_json(base,'state/mvcrs_governance_drift.json', {'drift_score':0.3})
    write_json(base,'state/mvcrs_horizon_coherence.json', {'instability_score':0.3})
    write_json(base,'state/mvcrs_multi_horizon_ensemble.json', {'instability_7d':0.3})
    summary = base/'INSTRUCTION_EXECUTION_SUMMARY.md'
    summary.write_text('# Summary\n', encoding='utf-8')
    mod.run_gdse_engine()
    mod.run_gdse_engine()
    content = summary.read_text(encoding='utf-8').splitlines()
    markers = [ln for ln in content if 'MVCRS_GDSE:' in ln]
    assert len(markers) == 1


def test_reason_matrix_deterministic_ordering():
    base = make_env()
    write_json(base,'state/mvcrs_governance_drift.json', {'drift_score':0.55})
    write_json(base,'state/mvcrs_horizon_coherence.json', {'instability_score':0.52})
    write_json(base,'state/mvcrs_multi_horizon_ensemble.json', {'instability_7d':0.60})
    p1 = mod.build_stabilization_profile()['reason_matrix']
    p2 = mod.build_stabilization_profile()['reason_matrix']
    assert p1 == p2
    # Ensure sorted by abs contribution desc then name ordering
    contrib_vals = [abs(float(x.split(':')[1])) for x in p1]
    assert contrib_vals == sorted(contrib_vals, reverse=True)
