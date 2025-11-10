import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone


def load_module(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_regime_alerts", str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_dedupe_comment_within_window():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "check_regime_alerts.py")

        # Prepare current RSI below warning (warning severity)
        current = {"stability_index": 70.0, "timestamp": datetime.now(timezone.utc).isoformat()}
        write_json(root / "reports" / "regime_stability.json", current)
        # History
        write_json(root / "logs" / "regime_stability_history.json", {"rsi": [{"timestamp": current["timestamp"], "value": 70.0}]})
        # Existing alert log within 12h for same severity
        recent = datetime.now(timezone.utc) - timedelta(hours=12)
        write_json(root / "logs" / "regime_alerts.json", {
            "last_alert_time": recent.isoformat(),
            "severity": "warning",
            "issue_number": 123
        })

        # Run
        cwd = os.getcwd()
        os.chdir(root)
        try:
            # capture stdout
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main([
                    "--current", "reports/regime_stability.json",
                    "--history", "logs/regime_stability_history.json",
                    "--threshold-warning", "80",
                    "--threshold-critical", "50",
                    "--owner", "test-owner"
                ])
            out = json.loads(buf.getvalue())
            code = mod.main([
                "--current", "reports/regime_stability.json",
                "--history", "logs/regime_stability_history.json",
                "--threshold-warning", "80",
                "--threshold-critical", "50",
                "--owner", "test-owner"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        assert out["alert"] is True
        assert out["action"] in ("comment", "create")
        # Prefer comment when within dedupe window and issue exists
        assert out["action"] == "comment"


def test_create_issue_when_no_existing_and_critical():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "check_regime_alerts.py")

        # Prepare current RSI critical
        current = {"stability_index": 40.0, "timestamp": datetime.now(timezone.utc).isoformat()}
        write_json(root / "reports" / "regime_stability.json", current)
        # Minimal history
        write_json(root / "logs" / "regime_stability_history.json", {"rsi": [{"timestamp": current["timestamp"], "value": 40.0}]})

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
                    "--threshold-warning", "80",
                    "--threshold-critical", "50",
                    "--owner", "test-owner"
                ])
            out = json.loads(buf.getvalue())
            code = mod.main([
                "--current", "reports/regime_stability.json",
                "--history", "logs/regime_stability_history.json",
                "--threshold-warning", "80",
                "--threshold-critical", "50",
                "--owner", "test-owner"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        assert out["alert"] is True
        assert out["severity"] == "critical"
        assert out["action"] in ("create", "comment")
