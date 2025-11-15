from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_PATH = Path(__file__).resolve().parents[2] / 'api' / 'trust_guard_api.py'


def load_module(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("trust_guard_api", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore[attr-defined]
    return m


@pytest.fixture()
def api(tmp_path: Path, monkeypatch):
    # Use tmp root
    monkeypatch.setenv('TRUST_GUARD_ROOT', str(tmp_path))
    module = load_module(API_PATH)
    client = TestClient(module.app)
    return module, client, tmp_path


def test_status_basic(api):
    module, client, root = api
    r = client.get('/trust/status')
    assert r.status_code == 200
    j = r.json()
    assert 'locked' in j


def test_force_unlock_success(api):
    module, client, root = api
    # Prime state
    state_dir = root / 'state'
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / 'trust_lock_state.json').write_text(json.dumps({'locked': True, 'manual_unlocks_today': 0, 'manual_unlocks_last_reset': '2000-01-01'}), encoding='utf-8')
    r = client.post('/trust/force-unlock', json={'reason': 'maintenance', 'actor': 'tester'})
    assert r.status_code == 200
    j = r.json()
    assert j['locked'] is False
    # Log entries
    log_lines = (root / 'state' / 'trust_lock_log.jsonl').read_text(encoding='utf-8').splitlines()
    assert any('manual_unlock' in ln for ln in log_lines)


def test_force_unlock_limit_exceeded(api):
    module, client, root = api
    state_dir = root / 'state'
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / 'trust_lock_state.json').write_text(json.dumps({'locked': True, 'manual_unlocks_today': 2, 'manual_unlocks_last_reset': '2099-01-01'}), encoding='utf-8')
    r = client.post('/trust/force-unlock', json={'reason': 'maintenance', 'actor': 'tester'})
    assert r.status_code == 403

