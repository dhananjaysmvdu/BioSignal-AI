"""
Tests for Reflex Health Timeline Dashboard Generator

Verifies:
- HTML dashboard generation with timeline chart
- CSV compliance export with proper formatting
- Trend detection (improving/declining/stable)
- Rolling mean computation
- Audit marker update
- Graceful handling of missing data
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from importlib import util


def load_module(path: Path):
    """Dynamically load a Python module from file path."""
    spec = util.spec_from_file_location("module", path)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dashboard_with_complete_history():
    """Test dashboard generation with full 10-entry history."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_health_dashboard.py")
        
        (root / "reports").mkdir(parents=True)
        (root / "logs").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        
        # Create improving trend history
        history = []
        base_time = datetime(2025, 11, 11, 10, 0, 0)
        for i in range(10):
            health = 60 + (i * 3)  # 60% to 87%
            entry = {
                "timestamp": (base_time + timedelta(hours=i)).isoformat() + "Z",
                "health_score": health,
                "classification": "Optimal Reflex Health" if health >= 80 else "Stable",
                "emoji": "🟢" if health >= 80 else "🟡",
                "components": {
                    "rei": {"value": 2.0 + i * 0.8},
                    "mpi": {"value": 65.0 + i * 2.5},
                    "confidence": {"value": 0.65 + i * 0.03},
                    "rri": {"value": 3.0 + i * 1.5}
                }
            }
            history.append(entry)
        
        (root / "logs" / "reflex_self_audit_history.json").write_text(
            json.dumps(history), encoding="utf-8"
        )
        (root / "reports" / "reflex_self_audit.json").write_text(
            json.dumps(history[-1]), encoding="utf-8"
        )
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        import os
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--self-audit", "reports/reflex_self_audit.json",
                "--history", "logs/reflex_self_audit_history.json",
                "--output", "reports/reflex_health_dashboard.html",
                "--csv-export", "exports/reflex_health_timeline.csv",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Verify HTML dashboard
        html_path = root / "reports" / "reflex_health_dashboard.html"
        assert html_path.exists()
        html_content = html_path.read_text(encoding="utf-8")
        
        assert "healthChart" in html_content
        assert "87.0%" in html_content
        assert "Optimal Reflex Health" in html_content
        assert "improving" in html_content
        assert "Rolling Mean" in html_content or "rollingMeans" in html_content
        
        # Verify CSV export
        csv_path = root / "exports" / "reflex_health_timeline.csv"
        assert csv_path.exists()
        csv_content = csv_path.read_text(encoding="utf-8")
        
        assert "timestamp,rei_score,mpi_score,confidence,rri_score,health_score,classification" in csv_content
        assert "This report is auto-generated for governance audit transparency" in csv_content
        
        csv_lines = [l for l in csv_content.split("\n") if l.strip() and not l.startswith("#")]
        assert len(csv_lines) == 11  # header + 10 data rows
        
        # Verify audit marker
        audit_path = root / "reports" / "audit_summary.md"
        audit_content = audit_path.read_text(encoding="utf-8")
        
        assert "REFLEX_HEALTH_DASHBOARD:BEGIN" in audit_content
        assert "10-run timeline & CSV export available" in audit_content


def test_improving_trend_detection():
    """Test trend detection for improving health scores."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_health_dashboard.py")
        
        (root / "reports").mkdir(parents=True)
        (root / "logs").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        
        # Create clear improving trend
        history = []
        base_time = datetime(2025, 11, 11, 10, 0, 0)
        for i in range(6):
            health = 55 + (i * 6)  # 55% to 85% - clear improvement
            entry = {
                "timestamp": (base_time + timedelta(hours=i)).isoformat() + "Z",
                "health_score": health,
                "classification": "Stable",
                "emoji": "🟡",
                "components": {}
            }
            history.append(entry)
        
        (root / "logs" / "reflex_self_audit_history.json").write_text(
            json.dumps(history), encoding="utf-8"
        )
        (root / "reports" / "reflex_self_audit.json").write_text(
            json.dumps(history[-1]), encoding="utf-8"
        )
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        import os
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--self-audit", "reports/reflex_self_audit.json",
                "--history", "logs/reflex_self_audit_history.json",
                "--output", "reports/reflex_health_dashboard.html",
                "--csv-export", "exports/reflex_health_timeline.csv",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        html_content = (root / "reports" / "reflex_health_dashboard.html").read_text(encoding="utf-8")
        assert "improving" in html_content


def test_declining_trend_detection():
    """Test trend detection for declining health scores."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_health_dashboard.py")
        
        (root / "reports").mkdir(parents=True)
        (root / "logs").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        
        # Create declining trend
        history = []
        base_time = datetime(2025, 11, 11, 10, 0, 0)
        for i in range(6):
            health = 85 - (i * 5)  # 85% to 60% - clear decline
            entry = {
                "timestamp": (base_time + timedelta(hours=i)).isoformat() + "Z",
                "health_score": health,
                "classification": "Stable",
                "emoji": "🟡",
                "components": {}
            }
            history.append(entry)
        
        (root / "logs" / "reflex_self_audit_history.json").write_text(
            json.dumps(history), encoding="utf-8"
        )
        (root / "reports" / "reflex_self_audit.json").write_text(
            json.dumps(history[-1]), encoding="utf-8"
        )
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        import os
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--self-audit", "reports/reflex_self_audit.json",
                "--history", "logs/reflex_self_audit_history.json",
                "--output", "reports/reflex_health_dashboard.html",
                "--csv-export", "exports/reflex_health_timeline.csv",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        html_content = (root / "reports" / "reflex_health_dashboard.html").read_text(encoding="utf-8")
        assert "declining" in html_content


def test_stable_trend_detection():
    """Test trend detection for stable health scores."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_health_dashboard.py")
        
        (root / "reports").mkdir(parents=True)
        (root / "logs").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        
        # Create stable trend with minor fluctuations
        history = []
        base_time = datetime(2025, 11, 11, 10, 0, 0)
        for i in range(6):
            health = 72 + (i % 2)  # 72-73% - stable
            entry = {
                "timestamp": (base_time + timedelta(hours=i)).isoformat() + "Z",
                "health_score": health,
                "classification": "Stable",
                "emoji": "🟡",
                "components": {}
            }
            history.append(entry)
        
        (root / "logs" / "reflex_self_audit_history.json").write_text(
            json.dumps(history), encoding="utf-8"
        )
        (root / "reports" / "reflex_self_audit.json").write_text(
            json.dumps(history[-1]), encoding="utf-8"
        )
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        import os
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--self-audit", "reports/reflex_self_audit.json",
                "--history", "logs/reflex_self_audit_history.json",
                "--output", "reports/reflex_health_dashboard.html",
                "--csv-export", "exports/reflex_health_timeline.csv",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        html_content = (root / "reports" / "reflex_health_dashboard.html").read_text(encoding="utf-8")
        assert "stable" in html_content


def test_compliance_table_last_5():
    """Test that compliance table shows last 5 runs with trend emojis."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_health_dashboard.py")
        
        (root / "reports").mkdir(parents=True)
        (root / "logs").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        
        # Create history with 8 entries
        history = []
        base_time = datetime(2025, 11, 11, 10, 0, 0)
        for i in range(8):
            health = 65 + (i * 2)
            entry = {
                "timestamp": (base_time + timedelta(hours=i)).isoformat() + "Z",
                "health_score": health,
                "classification": "Stable",
                "emoji": "🟡",
                "components": {}
            }
            history.append(entry)
        
        (root / "logs" / "reflex_self_audit_history.json").write_text(
            json.dumps(history), encoding="utf-8"
        )
        (root / "reports" / "reflex_self_audit.json").write_text(
            json.dumps(history[-1]), encoding="utf-8"
        )
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        import os
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--self-audit", "reports/reflex_self_audit.json",
                "--history", "logs/reflex_self_audit_history.json",
                "--output", "reports/reflex_health_dashboard.html",
                "--csv-export", "exports/reflex_health_timeline.csv",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        html_content = (root / "reports" / "reflex_health_dashboard.html").read_text(encoding="utf-8")
        
        # Should show compliance table
        assert "<table>" in html_content
        assert "Compliance Summary" in html_content
        
        # Should show trend emojis
        assert "📈" in html_content or "📉" in html_content or "➡️" in html_content


def test_idempotent_audit_marker():
    """Test that running twice replaces marker instead of duplicating."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_health_dashboard.py")
        
        (root / "reports").mkdir(parents=True)
        (root / "logs").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        
        history = [{
            "timestamp": "2025-11-11T10:00:00Z",
            "health_score": 75.0,
            "classification": "Stable",
            "emoji": "🟡",
            "components": {}
        }]
        
        (root / "logs" / "reflex_self_audit_history.json").write_text(
            json.dumps(history), encoding="utf-8"
        )
        (root / "reports" / "reflex_self_audit.json").write_text(
            json.dumps(history[0]), encoding="utf-8"
        )
        
        # Pre-existing audit with marker
        initial_audit = """# Audit Summary

<!-- REFLEX_HEALTH_DASHBOARD:BEGIN -->
Old dashboard content
<!-- REFLEX_HEALTH_DASHBOARD:END -->

Other content.
"""
        (root / "reports" / "audit_summary.md").write_text(
            initial_audit, encoding="utf-8"
        )
        
        import os
        cwd = os.getcwd()
        os.chdir(root)
        try:
            # Run twice
            mod.main([
                "--self-audit", "reports/reflex_self_audit.json",
                "--history", "logs/reflex_self_audit_history.json",
                "--output", "reports/reflex_health_dashboard.html",
                "--csv-export", "exports/reflex_health_timeline.csv",
                "--audit-summary", "reports/audit_summary.md"
            ])
            
            mod.main([
                "--self-audit", "reports/reflex_self_audit.json",
                "--history", "logs/reflex_self_audit_history.json",
                "--output", "reports/reflex_health_dashboard.html",
                "--csv-export", "exports/reflex_health_timeline.csv",
                "--audit-summary", "reports/audit_summary.md"
            ])
        finally:
            os.chdir(cwd)
        
        audit_content = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        
        # Should have exactly one BEGIN and one END
        assert audit_content.count("REFLEX_HEALTH_DASHBOARD:BEGIN") == 1
        assert audit_content.count("REFLEX_HEALTH_DASHBOARD:END") == 1
        
        # Should not contain old content
        assert "Old dashboard content" not in audit_content
        
        # Should contain new content
        assert "timeline & CSV export available" in audit_content
        assert "Other content" in audit_content


def test_missing_data_graceful_handling():
    """Test graceful handling when data files are missing."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "generate_reflex_health_dashboard.py")
        
        (root / "reports").mkdir(parents=True)
        (root / "logs").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        
        # No input files - should use defaults
        import os
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--self-audit", "reports/reflex_self_audit.json",
                "--history", "logs/reflex_self_audit_history.json",
                "--output", "reports/reflex_health_dashboard.html",
                "--csv-export", "exports/reflex_health_timeline.csv",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Should still generate outputs
        assert (root / "reports" / "reflex_health_dashboard.html").exists()
        assert (root / "exports" / "reflex_health_timeline.csv").exists()
        
        html_content = (root / "reports" / "reflex_health_dashboard.html").read_text(encoding="utf-8")
        assert "50.0%" in html_content  # Default health score
        assert "Stable" in html_content  # Default classification
