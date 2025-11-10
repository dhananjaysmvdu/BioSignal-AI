import json
import os
import sys
import tempfile
from pathlib import Path


def load_module(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("generate_reflex_feedback_dashboard", str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_dashboard_generation_with_data():
    """Test dashboard generation with sample data."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_feedback_dashboard.py")
        
        # Setup reflex evaluation
        reflex = {
            "status": "ok",
            "timestamp": "2025-11-10T22:00:00Z",
            "policy_mode": "Caution Mode",
            "rei": 5.5,
            "classification": "Effective",
            "current_rsi": 85.0,
            "current_ghs": 75.0
        }
        write_json(root / "reports" / "reflex_evaluation.json", reflex)
        
        # Setup history
        history = {
            "rsi": [
                {"timestamp": "2025-11-10T20:00:00Z", "value": 70.0},
                {"timestamp": "2025-11-10T21:00:00Z", "value": 80.0},
                {"timestamp": "2025-11-10T22:00:00Z", "value": 85.0},
            ]
        }
        write_json(root / "logs" / "regime_stability_history.json", history)
        
        # Setup health
        health = {"GovernanceHealthScore": 75.0}
        write_json(root / "reports" / "governance_health.json", health)
        
        # Setup actions
        actions = [
            {"timestamp": "2025-11-10T20:30:00Z", "mode": "Caution Mode", "rsi": 70.0}
        ]
        write_json(root / "logs" / "regime_policy_actions.json", actions)
        
        # Run
        cwd = os.getcwd()
        os.chdir(root)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([
                    "--reflex", "reports/reflex_evaluation.json",
                    "--history", "logs/regime_stability_history.json",
                    "--health", "reports/governance_health.json",
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--output", "reports/reflex_feedback_dashboard.html",
                    "--audit-summary", "reports/audit_summary.md"
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Assertions
        assert out["status"] == "ok"
        assert out["last_rei"] == 5.5
        assert out["classification"] == "Effective"
        
        # Check HTML file created
        dashboard = root / "reports" / "reflex_feedback_dashboard.html"
        assert dashboard.exists()
        html_content = dashboard.read_text(encoding='utf-8')
        assert "Reflex Feedback Dashboard" in html_content
        assert "REI +5.50" in html_content
        assert "Effective" in html_content


def test_first_run_empty_data():
    """Test graceful handling when no reflex data exists yet."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_feedback_dashboard.py")
        
        # Empty data
        write_json(root / "reports" / "reflex_evaluation.json", {})
        write_json(root / "logs" / "regime_stability_history.json", {"rsi": []})
        write_json(root / "reports" / "governance_health.json", {})
        write_json(root / "logs" / "regime_policy_actions.json", [])
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([
                    "--reflex", "reports/reflex_evaluation.json",
                    "--history", "logs/regime_stability_history.json",
                    "--health", "reports/governance_health.json",
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--output", "reports/reflex_feedback_dashboard.html",
                    "--audit-summary", "reports/audit_summary.md"
                ])
            out = json.loads(buf.getvalue())
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Should still generate dashboard with neutral status
        assert out["status"] == "ok"
        dashboard = root / "reports" / "reflex_feedback_dashboard.html"
        assert dashboard.exists()


def test_idempotent_audit_marker():
    """Test that running twice doesn't duplicate markers."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_feedback_dashboard.py")
        
        reflex = {
            "status": "ok",
            "rei": 2.0,
            "classification": "Effective",
            "current_rsi": 85.0,
            "current_ghs": 70.0
        }
        write_json(root / "reports" / "reflex_evaluation.json", reflex)
        write_json(root / "logs" / "regime_stability_history.json", {"rsi": []})
        write_json(root / "reports" / "governance_health.json", {"GovernanceHealthScore": 70.0})
        write_json(root / "logs" / "regime_policy_actions.json", [])
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            # Run twice
            for _ in range(2):
                code = mod.main([
                    "--reflex", "reports/reflex_evaluation.json",
                    "--history", "logs/regime_stability_history.json",
                    "--health", "reports/governance_health.json",
                    "--actions-log", "logs/regime_policy_actions.json",
                    "--output", "reports/reflex_feedback_dashboard.html",
                    "--audit-summary", "reports/audit_summary.md"
                ])
                assert code == 0
        finally:
            os.chdir(cwd)
        
        # Check audit summary has only one pair of markers
        summary = (root / "reports" / "audit_summary.md").read_text()
        assert summary.count("<!-- REFLEX_FEEDBACK:BEGIN -->") == 1
        assert summary.count("<!-- REFLEX_FEEDBACK:END -->") == 1


def test_dashboard_html_structure():
    """Test that dashboard contains expected HTML elements."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_feedback_dashboard.py")
        
        reflex = {
            "status": "ok",
            "rei": -2.5,
            "classification": "Counterproductive",
            "current_rsi": 60.0,
            "current_ghs": 55.0,
            "policy_mode": "Critical Intervention"
        }
        write_json(root / "reports" / "reflex_evaluation.json", reflex)
        
        history = {"rsi": [{"timestamp": "2025-11-10T20:00:00Z", "value": 65.0}]}
        write_json(root / "logs" / "regime_stability_history.json", history)
        write_json(root / "reports" / "governance_health.json", {"GovernanceHealthScore": 55.0})
        write_json(root / "logs" / "regime_policy_actions.json", [])
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--reflex", "reports/reflex_evaluation.json",
                "--history", "logs/regime_stability_history.json",
                "--health", "reports/governance_health.json",
                "--actions-log", "logs/regime_policy_actions.json",
                "--output", "reports/reflex_feedback_dashboard.html",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Check HTML structure
        html = (root / "reports" / "reflex_feedback_dashboard.html").read_text(encoding='utf-8')
        assert "REI Trend (Reflex Effectiveness Index)" in html
        assert "RSI vs GHS Timeline" in html
        assert "Recent Reflex Decisions" in html
        assert "Counterproductive" in html
        assert "reiChart" in html
        assert "rsiGhsChart" in html
