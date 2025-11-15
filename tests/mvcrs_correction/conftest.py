import os, json, shutil, tempfile, pytest, sys
from pathlib import Path

# Add scripts path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts' / 'mvcrs'))

import mvcrs_correction_engine as correction

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix='mvcrs_corr_')
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def sandbox_env(monkeypatch, temp_dir):
    monkeypatch.setenv('MVCRS_BASE_DIR', temp_dir)
    monkeypatch.setenv('MVCRS_FAST_TEST', '1')
    return temp_dir

# Helpers

def write_json(base, rel, data):
    p = Path(base)/rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return str(p)

@pytest.fixture
def verifier_ok(sandbox_env):
    write_json(sandbox_env, 'state/challenge_verifier_state.json', {'status':'ok','timestamp':'T'})
    return sandbox_env

@pytest.fixture
def verifier_warning(sandbox_env):
    write_json(sandbox_env, 'state/challenge_verifier_state.json', {'status':'warning','timestamp':'T'})
    return sandbox_env

@pytest.fixture
def verifier_failed(sandbox_env):
    write_json(sandbox_env, 'state/challenge_verifier_state.json', {'status':'failed','timestamp':'T'})
    return sandbox_env

@pytest.fixture
def trust_lock_engaged(verifier_failed):
    write_json(verifier_failed, 'state/trust_lock_state.json', {'locked': True})
    return verifier_failed

@pytest.fixture
def safety_brake_engaged(verifier_failed):
    write_json(verifier_failed, 'state/safety_brake_state.json', {'engaged': True})
    return verifier_failed
