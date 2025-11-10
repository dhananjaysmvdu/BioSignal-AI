import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def load_module(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("governance_regime_policy_engine", str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_critical_intervention_decreasing():
    """Test critical RSI with decreasing trend triggers critical intervention."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_regime_policy_engine.py")
        
        # Setup: RSI = 40 (critical), decreasing trend
        current = {"stability_index": 40.0, "timestamp": datetime.now(timezone.utc).isoformat()}
        write_json(root / "reports" / "regime_stability.json", current)
        
        # History showing decline: 80 -> 70 -> 60 -> 50 -> 40
        history = {
            "rsi": [
                {"timestamp": "2025-11-10T20:00:00Z", "value": 80.0},
                {"timestamp": "2025-11-10T21:00:00Z", "value": 70.0},
                {"timestamp": "2025-11-10T22:00:00Z", "value": 60.0},
                {"timestamp": "2025-11-10T23:00:00Z", "value": 50.0},
                {"timestamp": "2025-11-11T00:00:00Z", "value": 40.0},
            ]
        }
        write_json(root / "logs" / "regime_stability_history.json", history)
        
        # Initial policy
        policy = {
            "governance_policy": {
                "learning_rate_factor": 1.0,
                "audit_frequency_days": 7,
                "stabilization_mode": "monitor"
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
                    "--current", "reports/regime_stability.json",
                    "--history", "logs/regime_stability_history.json",
                    "--policy", "configs/governance_policy.json",
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--audit-summary", "reports/audit_summary.md"
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Assertions
        assert out["mode"] == "Critical Intervention"
        assert out["learning_rate_factor"] == 0.8  # 1.0 * 0.8
        assert out["audit_frequency_days"] == 3  # max(3, 7//2)
        assert out["stabilization_mode"] == "active"
        
        # Check policy file was updated
        updated_policy = json.loads((root / "configs" / "governance_policy.json").read_text())
        gp = updated_policy.get("governance_policy", updated_policy)
        assert gp["learning_rate_factor"] == 0.8
        assert gp["audit_frequency_days"] == 3
        assert gp["stabilization_mode"] == "active"


def test_caution_mode():
    """Test RSI in caution range (50-80) triggers caution mode."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_regime_policy_engine.py")
        
        # Setup: RSI = 65 (caution)
        current = {"stability_index": 65.0, "timestamp": datetime.now(timezone.utc).isoformat()}
        write_json(root / "reports" / "regime_stability.json", current)
        
        history = {"rsi": [{"timestamp": "2025-11-11T00:00:00Z", "value": 65.0}]}
        write_json(root / "logs" / "regime_stability_history.json", history)
        
        policy = {
            "governance_policy": {
                "learning_rate_factor": 1.0,
                "audit_frequency_days": 8,
                "stabilization_mode": "monitor"
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
                    "--current", "reports/regime_stability.json",
                    "--history", "logs/regime_stability_history.json",
                    "--policy", "configs/governance_policy.json",
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--audit-summary", "reports/audit_summary.md"
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Assertions
        assert out["mode"] == "Caution Mode"
        assert out["learning_rate_factor"] == 0.9  # 1.0 * 0.9
        assert out["audit_frequency_days"] == 6  # round(8 * 0.75)
        assert out["stabilization_mode"] == "monitor"


def test_normal_operation():
    """Test high RSI (>=80) triggers normal operation with rate increase."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_regime_policy_engine.py")
        
        # Setup: RSI = 95 (normal)
        current = {"stability_index": 95.0, "timestamp": datetime.now(timezone.utc).isoformat()}
        write_json(root / "reports" / "regime_stability.json", current)
        
        history = {"rsi": [{"timestamp": "2025-11-11T00:00:00Z", "value": 95.0}]}
        write_json(root / "logs" / "regime_stability_history.json", history)
        
        policy = {
            "governance_policy": {
                "learning_rate_factor": 1.0,
                "audit_frequency_days": 7,
                "stabilization_mode": "monitor"
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
                    "--current", "reports/regime_stability.json",
                    "--history", "logs/regime_stability_history.json",
                    "--policy", "configs/governance_policy.json",
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--audit-summary", "reports/audit_summary.md"
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Assertions
        assert out["mode"] == "Normal Operation"
        assert out["learning_rate_factor"] == 1.2  # min(1.0 * 1.2, 1.5)
        assert out["audit_frequency_days"] == 7  # unchanged
        assert out["stabilization_mode"] == "adaptive"


def test_idempotent_audit_update():
    """Test that running twice doesn't duplicate audit markers."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_regime_policy_engine.py")
        
        current = {"stability_index": 85.0}
        write_json(root / "reports" / "regime_stability.json", current)
        
        history = {"rsi": [{"timestamp": "2025-11-11T00:00:00Z", "value": 85.0}]}
        write_json(root / "logs" / "regime_stability_history.json", history)
        
        policy = {"learning_rate_factor": 1.0, "audit_frequency_days": 7}
        write_json(root / "configs" / "governance_policy.json", policy)
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            # Run twice
            for _ in range(2):
                code = mod.main([
                    "--current", "reports/regime_stability.json",
                    "--history", "logs/regime_stability_history.json",
                    "--policy", "configs/governance_policy.json",
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--audit-summary", "reports/audit_summary.md"
                ])
                assert code == 0
        finally:
            os.chdir(cwd)
        
        # Check audit summary has only one pair of markers
        summary = (root / "reports" / "audit_summary.md").read_text()
        assert summary.count("<!-- REGIME_POLICY:BEGIN -->") == 1
        assert summary.count("<!-- REGIME_POLICY:END -->") == 1
