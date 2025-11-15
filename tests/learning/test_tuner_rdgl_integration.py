#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def patch_tuner_paths(tmp_path, monkeypatch):
    root = tmp_path
    state = root / "state"
    federation = root / "federation"
    forensics = root / "forensics" / "forecast"

    state.mkdir(parents=True)
    federation.mkdir(parents=True)
    forensics.mkdir(parents=True)

    import scripts.policy.autonomous_threshold_tuner as atte

    monkeypatch.setattr(atte, "STATE_DIR", state)
    monkeypatch.setattr(atte, "FEDERATION_DIR", federation)
    monkeypatch.setattr(atte, "FORENSICS_DIR", root / "forensics")
    monkeypatch.setattr(atte, "AUDIT_FILE", root / "audit_summary.md")

    monkeypatch.setattr(atte, "THRESHOLD_POLICY", state / "threshold_policy.json")
    monkeypatch.setattr(atte, "THRESHOLD_HISTORY", state / "threshold_tuning_history.jsonl")
    monkeypatch.setattr(atte, "POLICY_FUSION_STATE", state / "policy_fusion_state.json")

    # Baseline inputs
    (state / "policy_fusion_state.json").write_text(json.dumps({
        "fusion_level": "FUSION_GREEN",
        "inputs": {"trust_locked": False, "safety_brake_engaged": False}
    }), encoding="utf-8")

    return atte, state


def write_thresholds(state: Path, integrity_green=90.0):
    state.mkdir(parents=True, exist_ok=True)
    base = {
        "integrity": {"green": integrity_green, "yellow": 85.0},
        "consensus": {"green": 95.0, "yellow": 90.0},
        "forecast": {"low": 5, "medium": 15, "high": 30},
        "responses": {"soft": 7, "hard": 10},
        "reputation": {"min_peer_score": 70.0},
        "status": "stable"
    }
    (state / "threshold_policy.json").write_text(json.dumps(base), encoding="utf-8")


def write_rdgl(state: Path, mode: str, rng):
    (state / "rdgl_policy_adjustments.json").write_text(json.dumps({
        "mode": mode,
        "shift_percent_range": rng,
        "last_updated": datetime.now(timezone.utc).isoformat()
    }), encoding="utf-8")


def test_relaxed_increases_shift_range(patch_tuner_paths):
    atte, state = patch_tuner_paths
    write_thresholds(state)
    write_rdgl(state, "relaxed", [1, 2])
    rc = atte.run_threshold_tuner(dry_run=False)
    assert rc == 0
    data = json.loads((state/"threshold_policy.json").read_text(encoding="utf-8"))
    assert data["rdgl_mode_used"] == "relaxed"
    assert data["rdgl_scaled_percent_range"][1] > 2.0  # 2 * 1.2 = 2.4


def test_tightening_reduces_shift_range(patch_tuner_paths):
    atte, state = patch_tuner_paths
    write_thresholds(state)
    write_rdgl(state, "tightening", [1, 2])
    rc = atte.run_threshold_tuner(dry_run=False)
    assert rc == 0
    data = json.loads((state/"threshold_policy.json").read_text(encoding="utf-8"))
    assert data["rdgl_mode_used"] == "tightening"
    assert 0.0 <= data["rdgl_scaled_percent_range"][1] < 2.0


def test_locked_produces_zero_range_and_locked_status(patch_tuner_paths):
    atte, state = patch_tuner_paths
    write_thresholds(state)
    write_rdgl(state, "locked", [1, 2])
    rc = atte.run_threshold_tuner(dry_run=False)
    assert rc == 0
    data = json.loads((state/"threshold_policy.json").read_text(encoding="utf-8"))
    assert data["rdgl_mode_used"] == "locked"
    assert data["rdgl_scaled_percent_range"] == [0.0, 0.0]
    assert data["status"] == "locked"


def test_normal_leaves_range_unchanged(patch_tuner_paths):
    atte, state = patch_tuner_paths
    write_thresholds(state)
    write_rdgl(state, "normal", [1, 2])
    rc = atte.run_threshold_tuner(dry_run=False)
    assert rc == 0
    data = json.loads((state/"threshold_policy.json").read_text(encoding="utf-8"))
    assert data["rdgl_mode_used"] == "normal"
    assert data["rdgl_scaled_percent_range"] == [1.0, 2.0]


def test_audit_marker_idempotent_and_updated(patch_tuner_paths):
    atte, state = patch_tuner_paths
    write_thresholds(state)
    write_rdgl(state, "normal", [1, 2])
    # Seed audit file
    audit = (state.parent / "audit_summary.md")
    audit.write_text("\n<!-- ATTE_RDGL_INTEGRATION: USED 2025-01-01T00:00:00+00:00 -->\n", encoding="utf-8")
    atte.run_threshold_tuner(dry_run=False)
    text1 = audit.read_text(encoding="utf-8")
    atte.run_threshold_tuner(dry_run=False)
    text2 = audit.read_text(encoding="utf-8")
    assert text1.count("ATTE_RDGL_INTEGRATION: USED") == 1
    assert text2.count("ATTE_RDGL_INTEGRATION: USED") == 1


def test_no_rdgl_file_fallback(patch_tuner_paths):
    atte, state = patch_tuner_paths
    write_thresholds(state)
    # Do not write RDGL file
    rc = atte.run_threshold_tuner(dry_run=False)
    assert rc == 0
    data = json.loads((state/"threshold_policy.json").read_text(encoding="utf-8"))
    assert data["rdgl_mode_used"] in ("normal", "tightening", "relaxed", "locked")
    # Fallback default is [1,2]
    assert data["rdgl_shift_range_used"] == [1, 2]
    assert data["rdgl_scaled_percent_range"][1] <= 3.0
