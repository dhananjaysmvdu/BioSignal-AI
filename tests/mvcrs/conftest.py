"""Pytest fixtures for MV-CRS testing."""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_artifact_dir():
    """Create isolated temporary sandbox for artifact testing."""
    tmpdir = tempfile.mkdtemp(prefix="mvcrs_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def mock_env_with_basedir(temp_artifact_dir, monkeypatch):
    """Set MVCRS_BASE_DIR to isolated temp directory."""
    monkeypatch.setenv("MVCRS_BASE_DIR", temp_artifact_dir)
    return temp_artifact_dir


def ensure_dirs(base_dir: str, dirs: list[str]) -> None:
    """Create directory structure in base_dir."""
    for d in dirs:
        path = os.path.join(base_dir, d)
        os.makedirs(path, exist_ok=True)


def write_json(base_dir: str, rel_path: str, data: dict) -> str:
    """Write JSON artifact to base_dir/rel_path."""
    full_path = os.path.join(base_dir, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return full_path


def write_jsonl(base_dir: str, rel_path: str, lines: list[dict]) -> str:
    """Write JSONL artifact to base_dir/rel_path."""
    full_path = os.path.join(base_dir, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")
    return full_path


@pytest.fixture
def fixture_minimal_artifacts(mock_env_with_basedir):
    """Minimal valid artifacts (all mandatory, no optional)."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    write_jsonl(base_dir, "state/challenge_events.jsonl", [
        {"ts": 1000000000, "event": "test_event_1"},
    ])
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
        "event_count": 1,
    })
    
    return base_dir


@pytest.fixture
def fixture_full_artifacts_ok(mock_env_with_basedir):
    """Full artifact set with no deviations (status=ok expected)."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    write_jsonl(base_dir, "state/challenge_events.jsonl", [
        {"ts": 1000000000, "event": "test_event_1"},
        {"ts": 1000000001, "event": "test_event_2"},
    ])
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
        "event_count": 2,
    })
    write_json(base_dir, "federation/provenance_consensus.json", {
        "consensus_pct": 95.0,
    })
    write_json(base_dir, "state/rdgl_policy_adjustments.json", {
        "mode": "adaptive",
        "score": 85,
    })
    write_json(base_dir, "state/policy_fusion_state.json", {
        "inputs": {
            "policy": "RED",
            "weighted_consensus_pct": 95.0,
        },
    })
    write_json(base_dir, "state/policy_state.json", {
        "inputs": {
            "forecast_risk": "medium",
            "recent_responses": 3,
        },
    })
    write_json(base_dir, "state/trust_lock_state.json", {
        "locked": False,
    })
    
    return base_dir


@pytest.fixture
def fixture_type_a_missing_mandatory(mock_env_with_basedir):
    """TYPE_A deviation: missing mandatory file."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    # Missing challenge_events.jsonl (mandatory)
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
        "event_count": 0,
    })
    
    return base_dir


@pytest.fixture
def fixture_type_a_corrupt_jsonl(mock_env_with_basedir):
    """TYPE_A deviation: corrupt JSONL in challenge_events."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    # Write valid line then corrupt line
    full_path = os.path.join(base_dir, "state/challenge_events.jsonl")
    with open(full_path, "w", encoding="utf-8") as f:
        f.write('{"ts": 1000000000, "event": "valid"}\n')
        f.write('{ invalid json syntax }\n')
    
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
        "event_count": 2,
    })
    
    return base_dir


@pytest.fixture
def fixture_type_b_rdgl_locked_non_red_policy(mock_env_with_basedir):
    """TYPE_B deviation: RDGL locked but policy not RED."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    write_jsonl(base_dir, "state/challenge_events.jsonl", [
        {"ts": 1000000000, "event": "test"},
    ])
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
    })
    write_json(base_dir, "state/rdgl_policy_adjustments.json", {
        "mode": "locked_adaptive",
    })
    write_json(base_dir, "state/policy_fusion_state.json", {
        "inputs": {
            "policy": "GREEN",
            "weighted_consensus_pct": 95.0,
        },
    })
    
    return base_dir


@pytest.fixture
def fixture_type_b_low_consensus(mock_env_with_basedir):
    """TYPE_B deviation: consensus below 90%."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    write_jsonl(base_dir, "state/challenge_events.jsonl", [
        {"ts": 1000000000, "event": "test"},
    ])
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
    })
    write_json(base_dir, "state/policy_fusion_state.json", {
        "inputs": {
            "policy": "RED",
            "weighted_consensus_pct": 75.0,
        },
    })
    
    return base_dir


@pytest.fixture
def fixture_type_c_high_risk_low_responses(mock_env_with_basedir):
    """TYPE_C deviation: high risk with <2 responses."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    write_jsonl(base_dir, "state/challenge_events.jsonl", [
        {"ts": 1000000000, "event": "test"},
    ])
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
    })
    write_json(base_dir, "state/policy_state.json", {
        "inputs": {
            "forecast_risk": "high",
            "recent_responses": 0,
        },
    })
    
    return base_dir


@pytest.fixture
def fixture_type_c_low_risk_high_responses(mock_env_with_basedir):
    """TYPE_C deviation: low risk with >5 responses."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    write_jsonl(base_dir, "state/challenge_events.jsonl", [
        {"ts": 1000000000, "event": "test"},
    ])
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
    })
    write_json(base_dir, "state/policy_state.json", {
        "inputs": {
            "forecast_risk": "low",
            "recent_responses": 8,
        },
    })
    
    return base_dir


@pytest.fixture
def fixture_type_d_adaptive_response_under_trust_lock(mock_env_with_basedir):
    """TYPE_D deviation: adaptive response while trust_lock=True."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    write_jsonl(base_dir, "state/challenge_events.jsonl", [
        {"ts": 1000000000, "event": "test"},
    ])
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
    })
    write_json(base_dir, "state/trust_lock_state.json", {
        "locked": True,
    })
    write_jsonl(base_dir, "forensics/response_history.jsonl", [
        {
            "response_id": "resp_001",
            "event_type": "ADAPTIVE_RESPONSE",
            "status": "executed",
        },
    ])
    
    return base_dir


@pytest.fixture
def fixture_multiple_high_severity_a_and_b(mock_env_with_basedir):
    """Mixed high-severity deviations: missing mandatory + low consensus."""
    base_dir = mock_env_with_basedir
    ensure_dirs(base_dir, ["state", "federation", "forensics"])
    
    # Missing challenge_events.jsonl (high TYPE_A)
    write_json(base_dir, "state/challenges_chain_meta.json", {
        "chain_hash": "abc123",
    })
    # Low consensus causing TYPE_B medium (promoted to high due to TYPE_A)
    write_json(base_dir, "state/policy_fusion_state.json", {
        "inputs": {
            "policy": "RED",
            "weighted_consensus_pct": 75.0,
        },
    })
    
    return base_dir
