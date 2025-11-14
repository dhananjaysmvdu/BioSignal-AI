import os, json, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'mvcrs'))
import mvcrs_correction_engine as correction

def read_json(base, rel):
    p = Path(base)/rel
    return json.load(open(p,'r',encoding='utf-8')) if p.is_file() else None

# A. No-op case
def test_no_op_ok(verifier_ok):
    code = correction.main([])
    # No artifacts should be created
    assert not Path(verifier_ok,'state/mvcrs_last_correction.json').exists()
    assert not Path(verifier_ok,'state/mvcrs_correction_log.jsonl').exists()
    assert code == 0

# B. Soft correction case
def test_soft_corrections_warning(verifier_warning):
    code = correction.main([])
    last = read_json(verifier_warning,'state/mvcrs_last_correction.json')
    assert last is not None
    assert last['correction_type'] == 'soft'
    assert last['actions_hard'] == []
    # All logged actions are soft
    log_path = Path(verifier_warning,'state/mvcrs_correction_log.jsonl')
    lines = log_path.read_text(encoding='utf-8').strip().split('\n')
    assert all(json.loads(l)['action_scope']=='soft' for l in lines if l)
    # Undo instructions present
    assert all('undo' in json.loads(l) for l in lines if l)
    # Audit marker single
    audit = Path(verifier_warning,'docs/audit_summary.md').read_text(encoding='utf-8')
    assert audit.count('MVCRS_CORRECTION:') == 1
    assert code == 0

# C. Hard correction case
def test_hard_corrections_failed(verifier_failed):
    code = correction.main([])
    last = read_json(verifier_failed,'state/mvcrs_last_correction.json')
    assert last['correction_type'] == 'hard'
    assert len(last['actions_hard']) > 0
    # Log contains both scopes
    lines = Path(verifier_failed,'state/mvcrs_correction_log.jsonl').read_text(encoding='utf-8').strip().split('\n')
    scopes = {json.loads(l)['action_scope'] for l in lines if l}
    assert 'soft' in scopes and 'hard' in scopes
    assert code == 3

# D. Trust Lock Block
def test_trust_lock_blocks_hard(trust_lock_engaged):
    code = correction.main([])
    last = read_json(trust_lock_engaged,'state/mvcrs_last_correction.json')
    assert last['correction_type'] == 'soft_blocked'
    assert last['blocked_by_trust_lock'] is True
    assert last['actions_hard'] == []
    assert code == 4

# E. Safety Brake Block
def test_safety_brake_blocks_hard(safety_brake_engaged):
    code = correction.main([])
    last = read_json(safety_brake_engaged,'state/mvcrs_last_correction.json')
    assert last['correction_type'] == 'soft_blocked'
    assert last['blocked_by_safety_brake'] is True
    assert last['actions_hard'] == []
    assert code == 4

# F. Branch Creation on Forced Failure
def test_branch_creation_on_forced_failure(verifier_failed, monkeypatch):
    monkeypatch.setenv('MVCRS_FORCE_CORRECTION_FS_FAILURE','1')
    code = correction.main([])
    assert code == 7
    audit = Path(verifier_failed,'docs/audit_summary.md').read_text(encoding='utf-8')
    assert 'MVCRS_CORRECTION: FAILED' in audit

# G. Audit Idempotency
def test_audit_idempotency_soft(verifier_warning):
    correction.main([])
    correction.main([])
    audit = Path(verifier_warning,'docs/audit_summary.md').read_text(encoding='utf-8')
    assert audit.count('MVCRS_CORRECTION:') == 1

# H. Summary Update
def test_summary_update_soft(verifier_warning):
    # Pre-create summary
    Path(verifier_warning,'state').mkdir(exist_ok=True)
    (Path(verifier_warning,'state')/'challenge_summary.json').write_text(json.dumps({'verifier_status':'warning'}),encoding='utf-8')
    correction.main([])
    summary = read_json(verifier_warning,'state/challenge_summary.json')
    assert 'correction_type' in summary
    assert 'hard_count_24h' in summary
    assert 'blocked_by_trust_lock' in summary
    assert 'last_correction_ts' in summary
