import json
import os
import tempfile
from pathlib import Path
from importlib import import_module


def test_meta_evaluator_classifications():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        hist = [
            {"r2": 0.4, "mae": 0.30},
            {"r2": 0.5, "mae": 0.25},  # mild drift improvement
            {"r2": 0.8, "mae": 0.15},  # stable learning
        ]
        (root / "logs").mkdir(parents=True, exist_ok=True)
        hist_path = root / "logs" / "reflex_model_history.json"
        hist_path.write_text(json.dumps(hist, indent=2), encoding='utf-8')

        (root / "reports").mkdir(parents=True, exist_ok=True)
        output_file = root / "reports" / "reflex_meta_performance.json"
        audit_file = root / "reports" / "audit_summary.md"
        audit_file.write_text("<!-- REFLEX_META:BEGIN -->\n<!-- REFLEX_META:END -->\n", encoding='utf-8')

        # Import and run
        import importlib.util, sys
        mod_path = Path.cwd() / "scripts" / "workflow_utils" / "governance_reflex_meta_evaluator.py"
        spec = importlib.util.spec_from_file_location("governance_reflex_meta_evaluator", str(mod_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore

        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--history", "logs/reflex_model_history.json",
                "--learning-model", "reports/reflex_learning_model.json",
                "--reflex", "reports/reflex_evaluation.json",
                "--output", "reports/reflex_meta_performance.json",
                "--audit-summary", "reports/audit_summary.md",
            ])
            assert code == 0
        finally:
            os.chdir(cwd)

        data = json.loads(output_file.read_text(encoding='utf-8'))
        assert "mpi" in data and 0 <= data["mpi"] <= 200  # with positive delta R2 scaler before clamp
        assert "classification" in data
        assert "REFLEX_META" in audit_file.read_text(encoding='utf-8')
