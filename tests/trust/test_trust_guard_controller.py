from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'trust' / 'trust_guard_controller.py'


def load_module(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("trust_guard_controller", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore[attr-defined]
    return m


@pytest.fixture()
def env(tmp_path: Path, monkeypatch):
    # Sandbox ROOT for trust guard
    monkeypatch.setenv('TRUST_GUARD_ROOT', str(tmp_path))
    # Create policy defaults
    policy_dir = tmp_path / 'policy'
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / 'trust_guard_policy.json').write_text(json.dumps({
        'thresholds': {'integrity': 90, 'weighted_consensus': 92, 'reputation_index': 85},
        'lock_window_minutes': 60,
        'auto_unlock_after_minutes': 60,
        'max_manual_unlocks_per_day': 2
    }), encoding='utf-8')
    m = load_module(MODULE_PATH)
    return m, tmp_path


def write_metrics(root: Path, integrity: float, consensus: float, reputation: float):
    # Write integrity registry CSV
    exports = root / 'exports'
    exports.mkdir(parents=True, exist_ok=True)
    (exports / 'integrity_metrics_registry.csv').write_text('integrity\n{:.1f}\n'.format(integrity), encoding='utf-8')
    # Weighted consensus
    fed = root / 'federation'
    fed.mkdir(parents=True, exist_ok=True)
    (fed / 'weighted_consensus.json').write_text(json.dumps({'weighted_agreement_pct': consensus}), encoding='utf-8')
    # Reputation index
    (fed / 'reputation_index.json').write_text(json.dumps({'score': reputation}), encoding='utf-8')


def test_unlocked_when_all_above(env, tmp_path: Path):
    m, root = env
    write_metrics(root, 95.0, 95.0, 90.0)
    state = m.enforce(m.load_policy())
    assert state['locked'] is False


def test_locked_single_breach_reason(env):
    m, root = env
    write_metrics(root, 85.0, 93.0, 90.0)
    state = m.enforce(m.load_policy())
    assert state['locked'] is True
    assert state['reason'] == 'integrity'


def test_locked_multiple_breaches_reason_multiple(env):
    m, root = env
    write_metrics(root, 85.0, 80.0, 84.0)
    state = m.enforce(m.load_policy())
    assert state['locked'] is True
    assert state['reason'] == 'multiple'


def test_force_unlock_under_limit(env):
    m, root = env
    write_metrics(root, 85.0, 80.0, 84.0)
    # First enforce lock
    m.enforce(m.load_policy())
    s1 = m.force_unlock(m.load_policy(), 'testing', actor='tester')
    assert s1['locked'] is False
    assert s1['manual_unlocks_today'] == 1


def test_force_unlock_block_when_limit_reached(env):
    m, root = env
    write_metrics(root, 85.0, 80.0, 84.0)
    m.enforce(m.load_policy())
    m.force_unlock(m.load_policy(), 'first', actor='tester')
    m.force_unlock(m.load_policy(), 'second', actor='tester')
    result = m.force_unlock(m.load_policy(), 'third', actor='tester')
    assert result['status'] == 'limit_exceeded'


def test_override_bypass_respected(env):
    m, root = env
    write_metrics(root, 80.0, 80.0, 80.0)
    # Activate override
    state_dir = root / 'state'
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / 'override_state.json').write_text(json.dumps({'active': True}), encoding='utf-8')
    s = m.enforce(m.load_policy())
    assert s['locked'] is False
    assert s['bypass'] is True


def test_fs_failure_retry_and_fix_branch(env, monkeypatch):
    m, root = env
    write_metrics(root, 80.0, 80.0, 80.0)
    # Simulate write failure
    def bad_write(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(m, 'atomic_write_json', bad_write)
    with pytest.raises(OSError):
        m.enforce(m.load_policy())
    # Verify diagnostics file created
    assert any(p.name.startswith('trust_guard_failure_') for p in (root / 'diagnostics').iterdir())


def test_atomic_write(tmp_path: Path, env):
    m, root = env
    write_metrics(root, 95.0, 95.0, 95.0)
    s = m.enforce(m.load_policy())
    # Ensure .tmp cleaned up
    state_dir = root / 'state'
    assert not any(p.suffix == '.tmp' for p in state_dir.iterdir())
