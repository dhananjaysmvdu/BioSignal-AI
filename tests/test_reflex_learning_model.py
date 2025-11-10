import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType
import contextlib


def load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)  # type: ignore
    return module


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')


def marker_count(text: str, marker: str) -> int:
    return text.count(f"<!-- {marker}:BEGIN -->")


def build_actions(n=10, start=0.0):
    actions = []
    for i in range(n):
        actions.append({
            "timestamp": f"2025-11-10T22:{i:02d}:00Z",
            "mode": "Normal Operation" if i % 3 == 0 else ("Caution Mode" if i % 3 == 1 else "Critical Intervention"),
            "learning_rate_factor": 1.0 + 0.05 * (i % 5),
            "audit_frequency_days": 7 - (i % 3),
            "rsi": 70 + i,
            "ghs": 60 + i * 0.5,
            "rei": 0.5 * i  # increasing REI for positive R²
        })
    return actions


def build_history(n=10):
    return {
        "rsi": [
            {"timestamp": f"2025-11-10T22:{i:02d}:00Z", "value": 70 + i}
            for i in range(n)
        ]
    }


def test_happy_path_uses_sklearn_stub():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mod_path = Path.cwd() / "scripts" / "workflow_utils" / "governance_reflex_learning_model.py"
        mod = load_module(mod_path)

        # Prepare data
        write_json(root / "logs" / "regime_policy_actions.json", build_actions(12))
        write_json(root / "logs" / "regime_stability_history.json", build_history(12))
        write_json(root / "reports" / "governance_health.json", {"GovernanceHealthScore": 75.0})

        # Stub sklearn path regardless of availability
        def stub_train(features, targets):
            # Return a fake trained model with positive r2
            return {
                "method": "Ridge",
                "coefficients": {
                    "rsi_prev": 0.1,
                    "rsi_delta": 0.2,
                    "ghs_prev": 0.3,
                    "learning_rate_factor": 0.4,
                    "audit_freq": -0.1,
                    "policy_mode": 0.05,
                },
                "intercept": 0.0,
                "r2": 0.85,
                "mae": 0.2,
                "n_samples": len(targets),
            }
        mod.train_model_sklearn = stub_train  # type: ignore
        mod.SKLEARN_AVAILABLE = True  # force sklearn path

        # Run
        cwd = os.getcwd()
        os.chdir(root)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--reflex", "reports/reflex_evaluation.json",
                    "--history", "logs/regime_stability_history.json",
                    "--health", "reports/governance_health.json",
                    "--output", "reports/reflex_learning_model.json",
                    "--history-output", "logs/reflex_model_history.json",
                    "--audit-summary", "reports/audit_summary.md",
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)

        # Assertions
        model_json = root / "reports" / "reflex_learning_model.json"
        assert model_json.exists()
        data = json.loads(model_json.read_text(encoding='utf-8'))
        assert "r2_score" in data
        assert data.get("r2", 0) > 0
        # History
        hist = json.loads((root / "logs" / "reflex_model_history.json").read_text(encoding='utf-8'))
        assert isinstance(hist, list) and len(hist) >= 1
        # Audit marker idempotent
        audit = (root / "reports" / "audit_summary.md").read_text(encoding='utf-8')
        assert marker_count(audit, "REFLEX_LEARNING") == 1


def test_fallback_when_less_than_10_samples():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mod_path = Path.cwd() / "scripts" / "workflow_utils" / "governance_reflex_learning_model.py"
        mod = load_module(mod_path)

        write_json(root / "logs" / "regime_policy_actions.json", build_actions(5))
        write_json(root / "logs" / "regime_stability_history.json", build_history(5))
        write_json(root / "reports" / "governance_health.json", {"GovernanceHealthScore": 55.0})

        # Ensure fallback path by size
        mod.SKLEARN_AVAILABLE = True

        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--actions-log", "logs/regime_policy_actions.json",
                "--reflex", "reports/reflex_evaluation.json",
                "--history", "logs/regime_stability_history.json",
                "--health", "reports/governance_health.json",
                "--output", "reports/reflex_learning_model.json",
                "--history-output", "logs/reflex_model_history.json",
                "--audit-summary", "reports/audit_summary.md",
            ])
            assert code == 0
        finally:
            os.chdir(cwd)

        model_json = root / "reports" / "reflex_learning_model.json"
        assert model_json.exists()
        data = json.loads(model_json.read_text(encoding='utf-8'))
        assert data.get("method") == "WeightedAverage"
        assert "r2_score" in data
        # Audit marker idempotent
        audit = (root / "reports" / "audit_summary.md").read_text(encoding='utf-8')
        assert marker_count(audit, "REFLEX_LEARNING") == 1


def test_missing_sklearn_graceful():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mod_path = Path.cwd() / "scripts" / "workflow_utils" / "governance_reflex_learning_model.py"
        mod = load_module(mod_path)

        write_json(root / "logs" / "regime_policy_actions.json", build_actions(12))
        write_json(root / "logs" / "regime_stability_history.json", build_history(12))
        write_json(root / "reports" / "governance_health.json", {"GovernanceHealthScore": 65.0})

        # Force missing sklearn path
        mod.SKLEARN_AVAILABLE = False

        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--actions-log", "logs/regime_policy_actions.json",
                "--reflex", "reports/reflex_evaluation.json",
                "--history", "logs/regime_stability_history.json",
                "--health", "reports/governance_health.json",
                "--output", "reports/reflex_learning_model.json",
                "--history-output", "logs/reflex_model_history.json",
                "--audit-summary", "reports/audit_summary.md",
            ])
            assert code == 0
        finally:
            os.chdir(cwd)

        model_json = root / "reports" / "reflex_learning_model.json"
        assert model_json.exists()
        data = json.loads(model_json.read_text(encoding='utf-8'))
        assert data.get("method") == "WeightedAverage"
        audit = (root / "reports" / "audit_summary.md").read_text(encoding='utf-8')
        assert marker_count(audit, "REFLEX_LEARNING") == 1
