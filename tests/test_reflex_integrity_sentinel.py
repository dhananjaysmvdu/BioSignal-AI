"""
Tests for Reflex Integrity Sentinel

Ensures:
- Timestamps monotonic check
- Parameter coherence check
- Data integrity / completeness checks
- Cross-validation of RRI vs Confidence
- Marker idempotency and CRITICAL labeling
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from importlib import util


def load_module(path: Path):
    spec = util.spec_from_file_location("module", path)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def write_csv(path: Path, rows):
    lines = [
        "# Reflex Health Timeline - Compliance Export",
        "# Generated: 2025-11-11 12:00:00 UTC",
        "# This report is auto-generated for governance audit transparency.",
        "",
        "timestamp,rei_score,mpi_score,confidence,rri_score,health_score,classification",
    ]
    for r in rows:
        lines.append(
            f"{r['timestamp']},{r['rei']:.2f},{r['mpi']:.2f},{r['conf']:.2f},{r['rri']:.2f},{r['health']:.2f},{r['class']}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run_sentinel(mod, root: Path):
    old_cwd = os.getcwd()
    os.chdir(root)
    try:
        code = mod.main([
            "--policy", "reports/governance_policy.json",
            "--self-audit", "reports/reflex_self_audit.json",
            "--csv", "exports/reflex_health_timeline.csv",
            "--reinforcement", "reports/reflex_reinforcement.json",
            "--confidence", "reports/confidence_adaptation.json",
            "--output", "reports/reflex_integrity.json",
            "--audit-summary", "reports/audit_summary.md",
        ])
        assert code == 0
    finally:
        os.chdir(old_cwd)


def test_valid_integrity_passes():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_integrity_sentinel.py")

        # Inputs
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "exports").mkdir(parents=True, exist_ok=True)
        now = datetime(2025, 11, 11, 10, 0, 0, tzinfo=timezone.utc)
        rows = []
        for i in range(5):
            ts = (now + timedelta(minutes=10*i)).isoformat().replace("+00:00", "Z")
            rows.append({
                'timestamp': ts,
                'rei': 70 + i,
                'mpi': 75 + i,
                'conf': 0.7 + i*0.02,
                'rri': 5 + i*1.0,
                'health': 70 + i*2.5,
                'class': 'Stable' if i < 4 else 'Optimal Reflex Health'
            })
        write_csv(root / "exports" / "reflex_health_timeline.csv", rows)

        policy = {"learning_rate_factor": 1.05}
        (root / "reports" / "governance_policy.json").write_text(json.dumps(policy), encoding="utf-8")

        latest = {
            "health_score": rows[-1]['health'],
            "classification": rows[-1]['class'],
            "emoji": "🟢"
        }
        (root / "reports" / "reflex_self_audit.json").write_text(json.dumps(latest), encoding="utf-8")

        rri = {"rri": 12.0}
        conf = {"confidence_weight": 0.78}
        (root / "reports" / "reflex_reinforcement.json").write_text(json.dumps(rri), encoding="utf-8")
        (root / "reports" / "confidence_adaptation.json").write_text(json.dumps(conf), encoding="utf-8")

        (root / "reports" / "audit_summary.md").write_text("# Audit Summary\n\n", encoding="utf-8")

        run_sentinel(mod, root)

        result = json.loads((root / "reports" / "reflex_integrity.json").read_text(encoding="utf-8"))
        assert "integrity_score" in result
        assert "status" in result
        assert result["status"] == "ok"
        assert result["integrity_score"] >= 90.0


def test_timestamp_violation():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_integrity_sentinel.py")

        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "exports").mkdir(parents=True, exist_ok=True)
        now = datetime(2025, 11, 11, 10, 0, 0, tzinfo=timezone.utc)
        rows = []
        # Monotonic, then a violation
        for i in range(3):
            ts = (now + timedelta(minutes=10*i)).isoformat().replace("+00:00", "Z")
            rows.append({'timestamp': ts, 'rei': 70, 'mpi': 75, 'conf': 0.7, 'rri': 5, 'health': 70+i*2, 'class': 'Stable'})
        # Non-monotonic timestamp
        rows.append({'timestamp': rows[1]['timestamp'], 'rei': 73, 'mpi': 77, 'conf': 0.72, 'rri': 6, 'health': 76, 'class': 'Stable'})
        write_csv(root / "exports" / "reflex_health_timeline.csv", rows)

        (root / "reports" / "governance_policy.json").write_text(json.dumps({"learning_rate_factor": 1.0}), encoding="utf-8")
        (root / "reports" / "reflex_self_audit.json").write_text(json.dumps({"health_score": 76, "classification": "Stable"}), encoding="utf-8")
        (root / "reports" / "audit_summary.md").write_text("# Audit Summary\n\n", encoding="utf-8")

        run_sentinel(mod, root)
        result = json.loads((root / "reports" / "reflex_integrity.json").read_text(encoding="utf-8"))
        assert "integrity_score" in result
        assert "status" in result
        assert 78.0 <= result["integrity_score"] <= 85.0
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "REFLEX_INTEGRITY:BEGIN" in audit


def test_confidence_mismatch():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_integrity_sentinel.py")

        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "exports").mkdir(parents=True, exist_ok=True)
        now = datetime(2025, 11, 11, 10, 0, 0, tzinfo=timezone.utc)
        rows = []
        for i in range(3):
            ts = (now + timedelta(minutes=10*i)).isoformat().replace("+00:00", "Z")
            rows.append({'timestamp': ts, 'rei': 70+i, 'mpi': 75+i, 'conf': 0.3, 'rri': 40, 'health': 70+i*2, 'class': 'Stable'})
        write_csv(root / "exports" / "reflex_health_timeline.csv", rows)

        (root / "reports" / "governance_policy.json").write_text(json.dumps({"learning_rate_factor": 1.0}), encoding="utf-8")
        (root / "reports" / "reflex_self_audit.json").write_text(json.dumps({"health_score": rows[-1]['health'], "classification": "Stable"}), encoding="utf-8")
        (root / "reports" / "reflex_reinforcement.json").write_text(json.dumps({"rri": 40}), encoding="utf-8")
        (root / "reports" / "confidence_adaptation.json").write_text(json.dumps({"confidence_weight": 0.3}), encoding="utf-8")
        (root / "reports" / "audit_summary.md").write_text("# Audit Summary\n\n", encoding="utf-8")

        run_sentinel(mod, root)
        result = json.loads((root / "reports" / "reflex_integrity.json").read_text(encoding="utf-8"))
        assert "integrity_score" in result
        assert "status" in result
        # Warning exists but not critical
        assert result["status"] == "ok"
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "CRITICAL" not in audit


def test_critical_failure():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_integrity_sentinel.py")

        # Intentionally missing self-audit to trigger completeness violation
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "exports").mkdir(parents=True, exist_ok=True)
        (root / "reports" / "governance_policy.json").write_text(json.dumps({"learning_rate_factor": 1.4}), encoding="utf-8")
        # No self-audit written
        (root / "reports" / "audit_summary.md").write_text("# Audit Summary\n\n", encoding="utf-8")
        # Provide CSV with non-monotonic and out-of-range values to add violations
        now = datetime(2025, 11, 11, 10, 0, 0, tzinfo=timezone.utc)
        bad_rows = [
            {'timestamp': now.isoformat().replace("+00:00", "Z"), 'rei': 10, 'mpi': 50, 'conf': 0.5, 'rri': 0, 'health': 50, 'class': 'Stable'},
            {'timestamp': (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"), 'rei': 15, 'mpi': 55, 'conf': 0.6, 'rri': 10, 'health': 45, 'class': 'Stable'},
            # Non-monotonic timestamp (goes back)
            {'timestamp': now.isoformat().replace("+00:00", "Z"), 'rei': 20, 'mpi': 60, 'conf': 1.2, 'rri': 200, 'health': -5, 'class': 'Degraded Reflex'},
        ]
        write_csv(root / "exports" / "reflex_health_timeline.csv", bad_rows)

        run_sentinel(mod, root)
        result = json.loads((root / "reports" / "reflex_integrity.json").read_text(encoding="utf-8"))
        assert "integrity_score" in result
        assert "status" in result
        assert result["integrity_score"] < 70.0
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "CRITICAL" in audit


def test_marker_idempotency():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_integrity_sentinel.py")

        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "exports").mkdir(parents=True, exist_ok=True)
        now = datetime(2025, 11, 11, 10, 0, 0, tzinfo=timezone.utc)
        rows = []
        for i in range(3):
            ts = (now + timedelta(minutes=10*i)).isoformat().replace("+00:00", "Z")
            rows.append({'timestamp': ts, 'rei': 70+i, 'mpi': 75+i, 'conf': 0.7, 'rri': 5+i, 'health': 70+i*2, 'class': 'Stable'})
        write_csv(root / "exports" / "reflex_health_timeline.csv", rows)

        (root / "reports" / "governance_policy.json").write_text(json.dumps({"learning_rate_factor": 1.0}), encoding="utf-8")
        (root / "reports" / "reflex_self_audit.json").write_text(json.dumps({"health_score": rows[-1]['health'], "classification": "Stable"}), encoding="utf-8")

        # Seed audit with existing marker
        (root / "reports" / "audit_summary.md").write_text(
            """# Audit Summary

<!-- REFLEX_INTEGRITY:BEGIN -->
Old integrity content
<!-- REFLEX_INTEGRITY:END -->

Other content.
""",
            encoding="utf-8"
        )

        # Run twice
        run_sentinel(mod, root)
        run_sentinel(mod, root)

        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert audit.count("REFLEX_INTEGRITY:BEGIN") == 1
        assert audit.count("REFLEX_INTEGRITY:END") == 1
        assert "Old integrity content" not in audit
        assert "Other content." in audit
