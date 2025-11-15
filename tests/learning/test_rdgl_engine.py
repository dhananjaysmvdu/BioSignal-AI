#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    root = tmp_path
    state = root / "state"
    federation = root / "federation"
    forensics = root / "forensics" / "forecast"
    learning = root / "scripts" / "learning"

    state.mkdir(parents=True)
    federation.mkdir(parents=True)
    forensics.mkdir(parents=True)
    learning.mkdir(parents=True)

    # Ensure module import from workspace
    import sys
    sys.path.insert(0, str(learning))

    # Import modules from repo to patch paths
    from scripts.learning import reinforcement_governance_learning as rdgl

    # Redirect paths
    monkeypatch.setattr(rdgl, "STATE_DIR", state)
    monkeypatch.setattr(rdgl, "FEDERATION_DIR", federation)
    monkeypatch.setattr(rdgl, "FORENSICS_DIR", forensics)
    monkeypatch.setattr(rdgl, "AUDIT_FILE", root / "audit_summary.md")

    monkeypatch.setattr(rdgl, "THRESHOLD_POLICY", state / "threshold_policy.json")
    monkeypatch.setattr(rdgl, "POLICY_FUSION_STATE", state / "policy_fusion_state.json")
    monkeypatch.setattr(rdgl, "ADAPTIVE_RESPONSE_HISTORY", state / "adaptive_response_history.jsonl")
    monkeypatch.setattr(rdgl, "FORECAST_FILE", forensics / "forensic_forecast.json")
    monkeypatch.setattr(rdgl, "PROVENANCE_CONSENSUS", federation / "provenance_consensus.json")
    monkeypatch.setattr(rdgl, "REPUTATION_INDEX", federation / "reputation_index.json")

    monkeypatch.setattr(rdgl, "RDGL_POLICY", state / "rdgl_policy_adjustments.json")
    monkeypatch.setattr(rdgl, "RDGL_REWARD_LOG", state / "rdgl_reward_log.jsonl")

    return {
        "root": root,
        "state": state,
        "federation": federation,
        "forensics": forensics,
    }


def write_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def append_jsonl(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")


def base_inputs(ws):
    # Minimal inputs used across tests
    write_json(ws["state"] / "threshold_policy.json", {"integrity": {"green": 90, "yellow": 85}})
    write_json(ws["state"] / "policy_fusion_state.json", {"fusion_level": "FUSION_GREEN", "inputs": {"safety_brake_engaged": False}})
    write_json(ws["forensics"] / "forensic_forecast.json", {"forecast_risk": "low"})
    write_json(ws["federation"] / "provenance_consensus.json", {"agreement_pct": 99.5, "peers_checked": 9})
    write_json(ws["federation"] / "reputation_index.json", {"scores": [{"peer": "a", "score": 90}]})


def test_reward_components_positive_signals(temp_workspace):
    ws = temp_workspace
    base_inputs(ws)

    # Seed previous reward log with high risk to detect improvement
    append_jsonl(ws["state"] / "rdgl_reward_log.jsonl", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reward": 0,
        "policy_score": 50.0,
        "forecast_risk": "high"
    })

    # Add self-healing actions in last 24h
    now = datetime.now(timezone.utc)
    for i in range(3):
        append_jsonl(ws["state"] / "adaptive_response_history.jsonl", {
            "timestamp": (now - timedelta(hours=i)).isoformat(),
            "action": "self_heal"
        })

    from scripts.learning.reinforcement_governance_learning import run_rdgl, RDGL_POLICY
    rc = run_rdgl(dry_run=False)
    assert rc == 0

    data = json.loads(RDGL_POLICY.read_text(encoding="utf-8"))
    assert data["reward_24h"] > 0, "Positive reward expected from improvements and self-heals"


def test_reward_penalties(temp_workspace):
    ws = temp_workspace
    base_inputs(ws)

    # Set fusion RED and safety brake engaged to induce penalties
    write_json(ws["state"] / "policy_fusion_state.json", {"fusion_level": "FUSION_RED", "inputs": {"safety_brake_engaged": True}})

    # Add unnecessary actions when green + low risk
    now = datetime.now(timezone.utc)
    for i in range(2):
        append_jsonl(ws["state"] / "adaptive_response_history.jsonl", {
            "timestamp": (now - timedelta(hours=i)).isoformat(),
            "action": "soft_alert"
        })

    from scripts.learning.reinforcement_governance_learning import run_rdgl, RDGL_POLICY
    rc = run_rdgl(dry_run=False)
    assert rc == 0
    data = json.loads(RDGL_POLICY.read_text(encoding="utf-8"))
    assert data["reward_24h"] <= 0, "Penalty expected when RED + brake + unnecessary actions"


def test_policy_score_updates_and_clamp(temp_workspace):
    ws = temp_workspace
    base_inputs(ws)

    # Start with near max score to test clamp
    write_json(ws["state"] / "rdgl_policy_adjustments.json", {"policy_score": 99.5})

    from scripts.learning.reinforcement_governance_learning import run_rdgl, RDGL_POLICY
    rc = run_rdgl(dry_run=False)
    assert rc == 0
    data = json.loads(RDGL_POLICY.read_text(encoding="utf-8"))
    assert 0.0 <= data["policy_score"] <= 100.0


def test_behavior_modes_selection(temp_workspace):
    ws = temp_workspace
    base_inputs(ws)

    from scripts.learning.reinforcement_governance_learning import run_rdgl, RDGL_POLICY

    # Force high score
    write_json(ws["state"] / "rdgl_policy_adjustments.json", {"policy_score": 85.0})
    run_rdgl(dry_run=False)
    d = json.loads(RDGL_POLICY.read_text(encoding="utf-8"))
    assert d["mode"] == "Relaxed"

    # Mid score
    write_json(ws["state"] / "rdgl_policy_adjustments.json", {"policy_score": 55.0})
    run_rdgl(dry_run=False)
    d = json.loads(RDGL_POLICY.read_text(encoding="utf-8"))
    assert d["mode"] == "Normal"

    # Tightening
    write_json(ws["state"] / "rdgl_policy_adjustments.json", {"policy_score": 35.0})
    run_rdgl(dry_run=False)
    d = json.loads(RDGL_POLICY.read_text(encoding="utf-8"))
    assert d["mode"] == "Tightening"

    # Locked
    write_json(ws["state"] / "rdgl_policy_adjustments.json", {"policy_score": 15.0})
    run_rdgl(dry_run=False)
    d = json.loads(RDGL_POLICY.read_text(encoding="utf-8"))
    assert d["mode"] == "Locked"


def test_fix_branch_on_fs_failure(temp_workspace, monkeypatch):
    ws = temp_workspace
    base_inputs(ws)

    # Simulate persistent FS failure on write
    from scripts.learning import reinforcement_governance_learning as rdgl

    def mock_atomic_write(*args, **kwargs):
        raise IOError("Mocked FS failure")

    monkeypatch.setattr(rdgl, "atomic_write_json", mock_atomic_write)

    # Capture git commands
    git_cmds = []
    def mock_run(cmd, *args, **kwargs):
        git_cmds.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_run)

    rc = rdgl.run_rdgl(dry_run=False)
    assert rc == 1
    assert any("git" in str(c) and "checkout" in str(c) and "fix/rdgl-" in " ".join(c) for c in git_cmds)


def test_audit_marker_idempotent(temp_workspace):
    ws = temp_workspace
    base_inputs(ws)

    from scripts.learning import reinforcement_governance_learning as rdgl

    rdgl.run_rdgl(dry_run=False)
    rdgl.run_rdgl(dry_run=False)

    text = (rdgl.AUDIT_FILE).read_text(encoding="utf-8")
    assert text.count("RDGL: UPDATED") == 1
