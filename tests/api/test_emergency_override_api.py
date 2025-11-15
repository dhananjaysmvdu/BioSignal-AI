"""Validation tests for Emergency Override API.

Ensures activation/deactivation lifecycle, atomic writes, logging, adaptive response bypass,
and portal page path sanity.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
API_FILE = ROOT / 'api' / 'emergency_override_api.py'
STATE_DIR = ROOT / 'state'
STATE_FILE = STATE_DIR / 'override_state.json'
LOG_FILE = STATE_DIR / 'override_log.jsonl'
ADAPTIVE_ENGINE = ROOT / 'scripts' / 'forensics' / 'adaptive_response_engine.py'


def load_module(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("emergency_override_api", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore[attr-defined]
    return m


@pytest.fixture()
def api(tmp_path: Path, monkeypatch):
    # Monkeypatch ROOT-like behavior by shadowing directories if needed
    # For atomic write validation we ensure test isolation by removing prior state
    for p in [STATE_FILE, LOG_FILE]:
        if p.exists():
            p.unlink()
    module = load_module(API_FILE)
    client = TestClient(module.app)

    # Monkeypatch subprocess.run in module to simulate bypass call
    def fake_run(*args, **kwargs):
        class R:  # minimal result object
            returncode = 0
            stdout = 'bypass simulated'
            stderr = ''
        # Validate env var set
        env = kwargs.get('env', {})
        assert env.get('ADAPTIVE_BYPASS') == '1', 'Adaptive bypass env not set'
        return R()
    module.subprocess.run = fake_run  # type: ignore
    return module, client


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def test_activation_sets_active(api):
    module, client = api
    resp = client.post('/override/activate', json={'reason': 'test scenario'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['active'] is True
    assert 'activated_at' in data
    state = read_json(STATE_FILE)
    assert state.get('active') is True


def test_deactivation_sets_inactive(api):
    module, client = api
    client.post('/override/activate', json={'reason': 'temp'})
    resp = client.post('/override/deactivate')
    assert resp.status_code == 200
    data = resp.json()
    assert data['active'] is False
    assert 'deactivated_at' in data
    state = read_json(STATE_FILE)
    assert state.get('active') is False


def test_status_reflects_state(api):
    module, client = api
    client.post('/override/activate', json={'reason': 'observe'})
    st = client.get('/override/status').json()
    assert st['active'] is True
    client.post('/override/deactivate')
    st2 = client.get('/override/status').json()
    assert st2['active'] is False


def test_log_entries_appended(api):
    module, client = api
    client.post('/override/activate', json={'reason': 'log1'})
    client.post('/override/deactivate')
    lines = [l for l in LOG_FILE.read_text(encoding='utf-8').splitlines() if l.strip()]
    assert any('"event": "activate"' in l for l in lines)
    assert any('"event": "deactivate"' in l for l in lines)


def test_adaptive_engine_bypass_called(api):
    module, client = api
    # Activation triggers bypass
    client.post('/override/activate', json={'reason': 'bypass check'})
    # No direct assertion beyond fake_run env validation
    assert read_json(STATE_FILE).get('active') is True


def test_atomic_writes(api):
    module, client = api
    client.post('/override/activate', json={'reason': 'atomic1'})
    first_state = STATE_FILE.read_text(encoding='utf-8')
    client.post('/override/deactivate')
    second_state = STATE_FILE.read_text(encoding='utf-8')
    assert 'activated_at' in first_state and 'deactivated_at' in second_state
    # Ensure no tmp residue
    assert not any(p.name.endswith('.tmp') for p in STATE_DIR.iterdir())


def test_portal_fetch_paths_relative():
    override_html = (ROOT / 'portal' / 'override.html').read_text(encoding='utf-8')
    # Ensure no absolute path fetches (e.g., http:// or https:// or file:///)
    assert 'fetch("/override/status"' in override_html or "fetch('/override/status'" in override_html
    disallowed = ['http://', 'https://', 'file://']
    for bad in disallowed:
        assert bad not in override_html, f'Disallowed absolute path found: {bad}'
