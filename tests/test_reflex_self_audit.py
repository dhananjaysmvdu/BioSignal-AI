"""
Tests for Reflex Self-Audit Aggregator

Verifies:
- Health score calculation with weighted components
- Optimal (≥80), Stable (60-79), Degraded (<60) classifications
- Component normalization (REI, RRI)
- Trend tracking with rolling mean
- Idempotent audit marker replacement
- Graceful handling of missing inputs
"""

import json
import os
import tempfile
from pathlib import Path
from importlib import util


def load_module(path: Path):
    """Dynamically load a Python module from file path."""
    spec = util.spec_from_file_location("module", path)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def test_optimal_reflex_health():
    """Test health ≥ 80 classified as Optimal Reflex Health (🟢)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_self_audit.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "logs").mkdir(parents=True, exist_ok=True)
        
        # Strong positive metrics
        reflex_eval = {"rei": 8.0, "classification": "Effective"}
        (root / "reports" / "reflex_evaluation.json").write_text(
            json.dumps(reflex_eval), encoding="utf-8"
        )
        
        meta_performance = {"mpi": 88.0, "classification": "Stable learning"}
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        confidence_adaptation = {
            "confidence_weight": 0.9,
            "trust_status": "High trust"
        }
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        reinforcement = {"rri": 15.0, "classification": "Reinforcing"}
        (root / "reports" / "reflex_reinforcement.json").write_text(
            json.dumps(reinforcement), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--reflex-eval", "reports/reflex_evaluation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--reinforcement", "reports/reflex_reinforcement.json",
                "--output", "reports/reflex_self_audit.json",
                "--audit-summary", "reports/audit_summary.md",
                "--history", "logs/reflex_self_audit_history.json"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "reflex_self_audit.json").read_text(encoding="utf-8")
        )
        
        assert result["status"] == "ok"
        assert result["classification"] == "Optimal Reflex Health"
        assert result["emoji"] == "🟢"
        assert result["health_score"] >= 80.0
        
        # Verify components
        assert result["components"]["rei"]["value"] == 8.0
        assert result["components"]["mpi"]["value"] == 88.0
        assert result["components"]["confidence"]["value"] == 0.9
        assert result["components"]["rri"]["value"] == 15.0
        
        # Verify weights sum to 1.0
        total_weight = sum([
            result["components"]["rei"]["weight"],
            result["components"]["mpi"]["weight"],
            result["components"]["confidence"]["weight"],
            result["components"]["rri"]["weight"]
        ])
        assert total_weight == 1.0
        
        # Verify audit marker
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "REFLEX_SELF_AUDIT:BEGIN" in audit
        assert "🟢 Optimal Reflex Health" in audit
        assert "REI=Effective" in audit


def test_stable_classification():
    """Test health 60-79 classified as Stable (🟡)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_self_audit.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "logs").mkdir(parents=True, exist_ok=True)
        
        # Moderate metrics
        reflex_eval = {"rei": 2.0, "classification": "Effective"}
        (root / "reports" / "reflex_evaluation.json").write_text(
            json.dumps(reflex_eval), encoding="utf-8"
        )
        
        meta_performance = {"mpi": 72.0, "classification": "Stable learning"}
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        confidence_adaptation = {
            "confidence_weight": 0.7,
            "trust_status": "Moderate trust"
        }
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        reinforcement = {"rri": 5.0, "classification": "Neutral"}
        (root / "reports" / "reflex_reinforcement.json").write_text(
            json.dumps(reinforcement), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--reflex-eval", "reports/reflex_evaluation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--reinforcement", "reports/reflex_reinforcement.json",
                "--output", "reports/reflex_self_audit.json",
                "--audit-summary", "reports/audit_summary.md",
                "--history", "logs/reflex_self_audit_history.json"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "reflex_self_audit.json").read_text(encoding="utf-8")
        )
        
        assert result["classification"] == "Stable"
        assert result["emoji"] == "🟡"
        assert 60.0 <= result["health_score"] < 80.0
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "🟡 Stable" in audit


def test_degraded_reflex():
    """Test health < 60 classified as Degraded Reflex (🔴)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_self_audit.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "logs").mkdir(parents=True, exist_ok=True)
        
        # Poor metrics
        reflex_eval = {"rei": -6.0, "classification": "Counterproductive"}
        (root / "reports" / "reflex_evaluation.json").write_text(
            json.dumps(reflex_eval), encoding="utf-8"
        )
        
        meta_performance = {"mpi": 45.0, "classification": "Learning degradation"}
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        confidence_adaptation = {
            "confidence_weight": 0.3,
            "trust_status": "Low trust"
        }
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        reinforcement = {"rri": -18.0, "classification": "Counterproductive"}
        (root / "reports" / "reflex_reinforcement.json").write_text(
            json.dumps(reinforcement), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--reflex-eval", "reports/reflex_evaluation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--reinforcement", "reports/reflex_reinforcement.json",
                "--output", "reports/reflex_self_audit.json",
                "--audit-summary", "reports/audit_summary.md",
                "--history", "logs/reflex_self_audit_history.json"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "reflex_self_audit.json").read_text(encoding="utf-8")
        )
        
        assert result["classification"] == "Degraded Reflex"
        assert result["emoji"] == "🔴"
        assert result["health_score"] < 60.0
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "🔴 Degraded Reflex" in audit


def test_trend_tracking():
    """Test trend detection with rolling mean over multiple runs."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_self_audit.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "logs").mkdir(parents=True, exist_ok=True)
        
        # Setup consistent inputs
        reflex_eval = {"rei": 5.0, "classification": "Effective"}
        (root / "reports" / "reflex_evaluation.json").write_text(
            json.dumps(reflex_eval), encoding="utf-8"
        )
        
        meta_performance = {"mpi": 75.0, "classification": "Stable learning"}
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        confidence_adaptation = {"confidence_weight": 0.8, "trust_status": "High trust"}
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        reinforcement = {"rri": 8.0, "classification": "Neutral"}
        (root / "reports" / "reflex_reinforcement.json").write_text(
            json.dumps(reinforcement), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            # First run
            mod.main([
                "--reflex-eval", "reports/reflex_evaluation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--reinforcement", "reports/reflex_reinforcement.json",
                "--output", "reports/reflex_self_audit.json",
                "--audit-summary", "reports/audit_summary.md",
                "--history", "logs/reflex_self_audit_history.json"
            ])
            
            first_result = json.loads(
                (root / "reports" / "reflex_self_audit.json").read_text(encoding="utf-8")
            )
            
            # Second run with improved metrics
            reflex_eval["rei"] = 7.0
            (root / "reports" / "reflex_evaluation.json").write_text(
                json.dumps(reflex_eval), encoding="utf-8"
            )
            
            mod.main([
                "--reflex-eval", "reports/reflex_evaluation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--reinforcement", "reports/reflex_reinforcement.json",
                "--output", "reports/reflex_self_audit.json",
                "--audit-summary", "reports/audit_summary.md",
                "--history", "logs/reflex_self_audit_history.json"
            ])
            
            second_result = json.loads(
                (root / "reports" / "reflex_self_audit.json").read_text(encoding="utf-8")
            )
        finally:
            os.chdir(cwd)
        
        # Verify trend tracking
        assert first_result["trend"]["direction"] == "initial"
        assert first_result["trend"]["samples"] == 1
        
        assert second_result["trend"]["samples"] == 2
        assert second_result["trend"]["direction"] in ["improving", "stable"]
        assert "rolling_mean_10" in second_result["trend"]
        
        # Verify history file
        history = json.loads(
            (root / "logs" / "reflex_self_audit_history.json").read_text(encoding="utf-8")
        )
        assert len(history) == 2
        assert history[0]["health_score"] == first_result["health_score"]
        assert history[1]["health_score"] == second_result["health_score"]


def test_idempotent_marker_replacement():
    """Test running twice replaces marker instead of duplicating."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_self_audit.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "logs").mkdir(parents=True, exist_ok=True)
        
        # Minimal setup
        reflex_eval = {"rei": 3.0, "classification": "Effective"}
        (root / "reports" / "reflex_evaluation.json").write_text(
            json.dumps(reflex_eval), encoding="utf-8"
        )
        
        meta_performance = {"mpi": 70.0, "classification": "Stable learning"}
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        confidence_adaptation = {"confidence_weight": 0.75, "trust_status": "Moderate trust"}
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        reinforcement = {"rri": 2.0, "classification": "Neutral"}
        (root / "reports" / "reflex_reinforcement.json").write_text(
            json.dumps(reinforcement), encoding="utf-8"
        )
        
        # Pre-existing audit with marker
        initial_audit = """# Audit Summary

<!-- REFLEX_SELF_AUDIT:BEGIN -->
Old audit content here
<!-- REFLEX_SELF_AUDIT:END -->

Other sections remain.
"""
        (root / "reports" / "audit_summary.md").write_text(
            initial_audit, encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            # Run twice
            mod.main([
                "--reflex-eval", "reports/reflex_evaluation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--reinforcement", "reports/reflex_reinforcement.json",
                "--output", "reports/reflex_self_audit.json",
                "--audit-summary", "reports/audit_summary.md",
                "--history", "logs/reflex_self_audit_history.json"
            ])
            
            mod.main([
                "--reflex-eval", "reports/reflex_evaluation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--reinforcement", "reports/reflex_reinforcement.json",
                "--output", "reports/reflex_self_audit.json",
                "--audit-summary", "reports/audit_summary.md",
                "--history", "logs/reflex_self_audit_history.json"
            ])
        finally:
            os.chdir(cwd)
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        
        # Should have exactly one BEGIN and one END marker
        assert audit.count("REFLEX_SELF_AUDIT:BEGIN") == 1
        assert audit.count("REFLEX_SELF_AUDIT:END") == 1
        
        # Should not contain old content
        assert "Old audit content here" not in audit
        
        # Should contain new content
        assert "Reflex Self-Audit" in audit
        assert "Other sections remain" in audit


def test_missing_inputs_use_defaults():
    """Test graceful handling when input files are missing."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_self_audit.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        (root / "logs").mkdir(parents=True, exist_ok=True)
        
        # No input files - should use defaults
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--reflex-eval", "reports/reflex_evaluation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--reinforcement", "reports/reflex_reinforcement.json",
                "--output", "reports/reflex_self_audit.json",
                "--audit-summary", "reports/audit_summary.md",
                "--history", "logs/reflex_self_audit_history.json"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "reflex_self_audit.json").read_text(encoding="utf-8")
        )
        
        # Should use neutral defaults
        assert result["status"] == "ok"
        assert result["components"]["rei"]["value"] == 0.0
        assert result["components"]["mpi"]["value"] == 50.0
        assert result["components"]["confidence"]["value"] == 0.5
        assert result["components"]["rri"]["value"] == 0.0
        
        # Should still compute health score (around 50% with defaults)
        assert 40.0 <= result["health_score"] <= 60.0
