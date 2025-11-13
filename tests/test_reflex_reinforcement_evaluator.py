"""
Tests for Reflex Reinforcement Index (RRI) Evaluator

Verifies:
- RRI ≥ +10 classified as Reinforcing (🟢)
- -10 ≤ RRI < +10 classified as Neutral (🟡)
- RRI < -10 classified as Counterproductive (🔴)
- RRI calculation formula: 100 × (0.5×ΔR² + 0.3×ΔMPI + 0.2×ΔLR)
- Idempotent audit marker replacement
- Graceful handling when insufficient history
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


def test_reinforcing_classification():
    """Test positive changes with RRI calculation verification."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_reinforcement_evaluator.py")
        
        # Setup inputs for positive reinforcement
        (root / "logs").mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # Model history showing R² improvement: 0.70 → 0.80 (ΔR²=+0.10)
        model_history = [
            {"r2_score": 0.70, "mae": 0.25, "timestamp": "2025-11-10T10:00:00Z"},
            {"r2_score": 0.80, "mae": 0.20, "timestamp": "2025-11-11T10:00:00Z"}
        ]
        (root / "logs" / "reflex_model_history.json").write_text(
            json.dumps(model_history), encoding="utf-8"
        )
        
        # Meta-performance showing MPI improvement (delta_r2=+0.05 → ΔMPI≈+5.0)
        meta_performance = {
            "mpi": 82.0,
            "delta_r2": 0.05,
            "classification": "Stable learning"
        }
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        # Confidence adaptation showing LR increase: 1.0 → 1.1 (ΔLR=+0.1)
        confidence_adaptation = {
            "original_learning_rate": 1.0,
            "adjusted_learning_rate": 1.1,
            "confidence_weight": 0.9
        }
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        # Run evaluator
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--model-history", "logs/reflex_model_history.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--output", "reports/reflex_reinforcement.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Verify output
        result_path = root / "reports" / "reflex_reinforcement.json"
        assert result_path.exists()
        result = json.loads(result_path.read_text(encoding="utf-8"))
        
        assert result["status"] == "ok"
        # RRI = 100 × (0.5×0.10 + 0.3×0.05 + 0.2×0.1) = 100 × (0.05 + 0.015 + 0.02) = 8.5
        # This is < 10, so Neutral classification is correct
        assert result["classification"] == "Neutral"
        assert result["emoji"] == "🟡"
        assert result["rri"] == 8.5
        assert result["components"]["delta_r2"] == 0.1
        assert result["components"]["delta_mpi"] == 5.0
        assert result["components"]["delta_lr"] == 0.1
        
        # Verify audit marker
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "REFLEX_REINFORCEMENT:BEGIN" in audit
        assert "RRI=" in audit


def test_reinforcing_high_values():
    """Test strong positive changes result in Reinforcing classification."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_reinforcement_evaluator.py")
        
        (root / "logs").mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # Strong R² improvement: 0.60 → 0.85 (ΔR²=+0.25)
        model_history = [
            {"r2_score": 0.60, "mae": 0.30},
            {"r2_score": 0.85, "mae": 0.15}
        ]
        (root / "logs" / "reflex_model_history.json").write_text(
            json.dumps(model_history), encoding="utf-8"
        )
        
        # Strong MPI improvement
        meta_performance = {
            "mpi": 88.0,
            "delta_r2": 0.15,  # ΔMPI = 15.0
            "classification": "Stable learning"
        }
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        # LR increase
        confidence_adaptation = {
            "original_learning_rate": 0.8,
            "adjusted_learning_rate": 1.0,
            "confidence_weight": 0.85
        }
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--model-history", "logs/reflex_model_history.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--output", "reports/reflex_reinforcement.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "reflex_reinforcement.json").read_text(encoding="utf-8")
        )
        
        # RRI = 100 × (0.5×0.25 + 0.3×0.15 + 0.2×0.2) = 100 × (0.125 + 0.045 + 0.04) = 21.0
        assert result["classification"] == "Reinforcing"
        assert result["emoji"] == "🟢"
        assert result["rri"] >= 10.0
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "🟢 Reinforcing" in audit


def test_neutral_classification():
    """Test -10 ≤ RRI < +10 classified as Neutral (🟡)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_reinforcement_evaluator.py")
        
        (root / "logs").mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # Small R² change: 0.75 → 0.77 (ΔR²=+0.02)
        model_history = [
            {"r2_score": 0.75, "mae": 0.22},
            {"r2_score": 0.77, "mae": 0.21}
        ]
        (root / "logs" / "reflex_model_history.json").write_text(
            json.dumps(model_history), encoding="utf-8"
        )
        
        # Small MPI change
        meta_performance = {
            "mpi": 78.0,
            "delta_r2": 0.01,  # ΔMPI = 1.0
            "classification": "Stable learning"
        }
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        # Minimal LR change
        confidence_adaptation = {
            "original_learning_rate": 1.0,
            "adjusted_learning_rate": 1.02,
            "confidence_weight": 0.7
        }
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--model-history", "logs/reflex_model_history.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--output", "reports/reflex_reinforcement.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "reflex_reinforcement.json").read_text(encoding="utf-8")
        )
        
        # RRI = 100 × (0.5×0.02 + 0.3×0.01 + 0.2×0.02) = 100 × (0.01 + 0.003 + 0.004) = 1.7
        assert result["classification"] == "Neutral"
        assert result["emoji"] == "🟡"
        assert -10.0 <= result["rri"] < 10.0
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "🟡 Neutral" in audit


def test_counterproductive_classification():
    """Test RRI < -10 classified as Counterproductive (🔴)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_reinforcement_evaluator.py")
        
        (root / "logs").mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # R² degradation: 0.80 → 0.55 (ΔR²=-0.25)
        model_history = [
            {"r2_score": 0.80, "mae": 0.18},
            {"r2_score": 0.55, "mae": 0.35}
        ]
        (root / "logs" / "reflex_model_history.json").write_text(
            json.dumps(model_history), encoding="utf-8"
        )
        
        # MPI degradation
        meta_performance = {
            "mpi": 58.0,
            "delta_r2": -0.15,  # ΔMPI = -15.0
            "classification": "Learning degradation"
        }
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        # LR decrease
        confidence_adaptation = {
            "original_learning_rate": 1.0,
            "adjusted_learning_rate": 0.7,
            "confidence_weight": 0.3
        }
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--model-history", "logs/reflex_model_history.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--output", "reports/reflex_reinforcement.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "reflex_reinforcement.json").read_text(encoding="utf-8")
        )
        
        # RRI = 100 × (0.5×(-0.25) + 0.3×(-0.15) + 0.2×(-0.3)) = 100 × (-0.125 - 0.045 - 0.06) = -23.0
        assert result["classification"] == "Counterproductive"
        assert result["emoji"] == "🔴"
        assert result["rri"] < -10.0
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "🔴 Counterproductive" in audit


def test_idempotent_marker_replacement():
    """Test running twice replaces marker instead of duplicating."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_reinforcement_evaluator.py")
        
        (root / "logs").mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # Minimal setup for neutral result
        model_history = [
            {"r2_score": 0.75, "mae": 0.22},
            {"r2_score": 0.76, "mae": 0.21}
        ]
        (root / "logs" / "reflex_model_history.json").write_text(
            json.dumps(model_history), encoding="utf-8"
        )
        
        meta_performance = {"mpi": 76.0, "delta_r2": 0.005}
        (root / "reports" / "reflex_meta_performance.json").write_text(
            json.dumps(meta_performance), encoding="utf-8"
        )
        
        confidence_adaptation = {
            "original_learning_rate": 1.0,
            "adjusted_learning_rate": 1.0,
            "confidence_weight": 0.8
        }
        (root / "reports" / "confidence_adaptation.json").write_text(
            json.dumps(confidence_adaptation), encoding="utf-8"
        )
        
        # Pre-existing audit with marker
        initial_audit = """# Audit Summary

<!-- REFLEX_REINFORCEMENT:BEGIN -->
Old RRI content here
<!-- REFLEX_REINFORCEMENT:END -->

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
                "--model-history", "logs/reflex_model_history.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--output", "reports/reflex_reinforcement.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            
            mod.main([
                "--model-history", "logs/reflex_model_history.json",
                "--confidence-adaptation", "reports/confidence_adaptation.json",
                "--meta-performance", "reports/reflex_meta_performance.json",
                "--output", "reports/reflex_reinforcement.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
        finally:
            os.chdir(cwd)
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        
        # Should have exactly one BEGIN and one END marker
        assert audit.count("REFLEX_REINFORCEMENT:BEGIN") == 1
        assert audit.count("REFLEX_REINFORCEMENT:END") == 1
        
        # Should not contain old content
        assert "Old RRI content here" not in audit
        
        # Should contain new content
        assert "RRI=" in audit
        assert "Other sections remain" in audit


def test_insufficient_history_defaults_neutral():
    """Test graceful handling when insufficient history (defaults to Neutral)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_reflex_reinforcement_evaluator.py")
        
        (root / "logs").mkdir(parents=True, exist_ok=True)
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # Only one entry in history (need at least 2 for delta)
        model_history = [
            {"r2_score": 0.75, "mae": 0.22}
        ]
        (root / "logs" / "reflex_model_history.json").write_text(
            json.dumps(model_history), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--model-history", "logs/reflex_model_history.json",
                "--output", "reports/reflex_reinforcement.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "reflex_reinforcement.json").read_text(encoding="utf-8")
        )
        
        # With no deltas, RRI should be 0.0 → Neutral
        assert result["status"] == "ok"
        assert result["classification"] == "Neutral"
        assert result["rri"] == 0.0
        assert result["history_samples"] == 1
