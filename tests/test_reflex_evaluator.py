import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def load_module(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("governance_reflex_evaluator", str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_effective_improvement():
    """Test effective improvement: positive delta_rsi and delta_ghs."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_evaluator.py")
        
        # Setup: policy action exists
        actions = [
            {
                "timestamp": "2025-11-10T20:00:00Z",
                "mode": "Caution Mode",
                "rsi": 70.0,
                "trend": "stable"
            }
        ]
        write_json(root / "logs" / "regime_policy_actions.json", actions)
        
        # History: RSI improved from 70 to 85
        history = {
            "rsi": [
                {"timestamp": "2025-11-10T19:00:00Z", "value": 70.0},
                {"timestamp": "2025-11-10T21:00:00Z", "value": 85.0},
            ]
        }
        write_json(root / "logs" / "regime_stability_history.json", history)
        
        # Health: GHS improved from 60 to 75
        health = {"GovernanceHealthScore": 75.0}
        write_json(root / "reports" / "governance_health.json", health)
        
        # Policy with previous GHS
        policy = {
            "governance_policy": {
                "previous_ghs": 60.0,
                "learning_rate_factor": 0.9
            }
        }
        write_json(root / "configs" / "governance_policy.json", policy)
        
        # Run
        cwd = os.getcwd()
        os.chdir(root)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--history", "logs/regime_stability_history.json",
                    "--health", "reports/governance_health.json",
                    "--policy", "configs/governance_policy.json",
                    "--output", "reports/reflex_evaluation.json",
                    "--audit-summary", "reports/audit_summary.md"
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Assertions
        # ΔRSI = 85 - 70 = 15
        # ΔGHS = 75 - 60 = 15
        # REI = 0.7 * 15 + 0.3 * 15 = 15
        assert out["delta_rsi"] == 15.0
        assert out["delta_ghs"] == 15.0
        assert out["rei"] == 15.0
        assert out["classification"] == "Effective"
        assert out["policy_mode"] == "Caution Mode"


def test_counterproductive_degradation():
    """Test counterproductive: negative deltas leading to REI < -1."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_evaluator.py")
        
        actions = [
            {
                "timestamp": "2025-11-10T20:00:00Z",
                "mode": "Critical Intervention",
                "rsi": 40.0
            }
        ]
        write_json(root / "logs" / "regime_policy_actions.json", actions)
        
        # History: RSI degraded from 40 to 30
        history = {
            "rsi": [
                {"timestamp": "2025-11-10T19:00:00Z", "value": 40.0},
                {"timestamp": "2025-11-10T21:00:00Z", "value": 30.0},
            ]
        }
        write_json(root / "logs" / "regime_stability_history.json", history)
        
        # Health: GHS degraded from 50 to 45
        health = {"GovernanceHealthScore": 45.0}
        write_json(root / "reports" / "governance_health.json", health)
        
        policy = {"governance_policy": {"previous_ghs": 50.0}}
        write_json(root / "configs" / "governance_policy.json", policy)
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--history", "logs/regime_stability_history.json",
                    "--health", "reports/governance_health.json",
                    "--policy", "configs/governance_policy.json",
                    "--output", "reports/reflex_evaluation.json",
                    "--audit-summary", "reports/audit_summary.md"
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Assertions
        # ΔRSI = 30 - 40 = -10
        # ΔGHS = 45 - 50 = -5
        # REI = 0.7 * (-10) + 0.3 * (-5) = -8.5
        assert out["delta_rsi"] == -10.0
        assert out["delta_ghs"] == -5.0
        assert out["rei"] == -8.5
        assert out["classification"] == "Counterproductive"


def test_neutral_no_change():
    """Test neutral classification: small or zero changes."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_evaluator.py")
        
        actions = [
            {
                "timestamp": "2025-11-10T20:00:00Z",
                "mode": "Normal Operation",
                "rsi": 85.0
            }
        ]
        write_json(root / "logs" / "regime_policy_actions.json", actions)
        
        # History: RSI stable 85 -> 85.5 (small change)
        history = {
            "rsi": [
                {"timestamp": "2025-11-10T19:00:00Z", "value": 85.0},
                {"timestamp": "2025-11-10T21:00:00Z", "value": 85.5},
            ]
        }
        write_json(root / "logs" / "regime_stability_history.json", history)
        
        # Health: GHS slight increase 70 -> 71
        health = {"GovernanceHealthScore": 71.0}
        write_json(root / "reports" / "governance_health.json", health)
        
        policy = {"governance_policy": {"previous_ghs": 70.0}}
        write_json(root / "configs" / "governance_policy.json", policy)
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--history", "logs/regime_stability_history.json",
                    "--health", "reports/governance_health.json",
                    "--policy", "configs/governance_policy.json",
                    "--output", "reports/reflex_evaluation.json",
                    "--audit-summary", "reports/audit_summary.md"
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Assertions
        # ΔRSI = 85.5 - 85 = 0.5
        # ΔGHS = 71 - 70 = 1
        # REI = 0.7 * 0.5 + 0.3 * 1 = 0.65
        assert abs(out["delta_rsi"] - 0.5) < 0.1
        assert abs(out["delta_ghs"] - 1.0) < 0.1
        assert abs(out["rei"] - 0.65) < 0.1
        assert out["classification"] == "Neutral"


def test_first_run_no_policy():
    """Test graceful first-run behavior when no policy action exists yet."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_evaluator.py")
        
        # No actions log (empty)
        write_json(root / "logs" / "regime_policy_actions.json", [])
        
        # Minimal data
        write_json(root / "logs" / "regime_stability_history.json", {"rsi": []})
        write_json(root / "reports" / "governance_health.json", {})
        write_json(root / "configs" / "governance_policy.json", {})
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--history", "logs/regime_stability_history.json",
                    "--health", "reports/governance_health.json",
                    "--policy", "configs/governance_policy.json",
                    "--output", "reports/reflex_evaluation.json",
                    "--audit-summary", "reports/audit_summary.md"
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Assertions
        assert out["classification"] == "Neutral"
        assert out["rei"] == 0.0
        assert "No policy action recorded yet" in out["note"]


def test_idempotent_marker_update():
    """Test that running twice doesn't duplicate markers."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_evaluator.py")
        
        actions = [{"timestamp": "2025-11-10T20:00:00Z", "mode": "Normal Operation", "rsi": 80.0}]
        write_json(root / "logs" / "regime_policy_actions.json", actions)
        
        history = {"rsi": [{"timestamp": "2025-11-10T19:00:00Z", "value": 80.0}, {"timestamp": "2025-11-10T21:00:00Z", "value": 82.0}]}
        write_json(root / "logs" / "regime_stability_history.json", history)
        
        health = {"GovernanceHealthScore": 75.0}
        write_json(root / "reports" / "governance_health.json", health)
        
        policy = {"previous_ghs": 74.0}
        write_json(root / "configs" / "governance_policy.json", policy)
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            # Run twice
            for _ in range(2):
                code = mod.main([
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--history", "logs/regime_stability_history.json",
                    "--health", "reports/governance_health.json",
                    "--policy", "configs/governance_policy.json",
                    "--output", "reports/reflex_evaluation.json",
                    "--audit-summary", "reports/audit_summary.md"
                ])
                assert code == 0
        finally:
            os.chdir(cwd)
        
        # Check audit summary has only one pair of markers
        summary = (root / "reports" / "audit_summary.md").read_text()
        assert summary.count("<!-- REFLEX_EVALUATION:BEGIN -->") == 1
        assert summary.count("<!-- REFLEX_EVALUATION:END -->") == 1
