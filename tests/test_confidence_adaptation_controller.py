"""
Tests for Confidence-Weighted Adaptation Controller

Verifies:
- High confidence (≥0.8) increases learning rate appropriately
- Moderate confidence (0.5-0.8) scales proportionally
- Low confidence (<0.5) reduces learning rate
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


def test_high_confidence_scaling():
    """Test confidence=0.9 increases learning rate (High trust)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_confidence_adaptation_controller.py")
        
        # Setup inputs
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # High confidence
        confidence_data = {"confidence_weight": 0.9}
        (root / "reports" / "forecast_confidence.json").write_text(
            json.dumps(confidence_data), encoding="utf-8"
        )
        
        # Baseline policy
        policy_data = {"learning_rate_factor": 1.0}
        (root / "reports" / "governance_policy.json").write_text(
            json.dumps(policy_data), encoding="utf-8"
        )
        
        # Initial audit
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        # Run controller
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--confidence", "reports/forecast_confidence.json",
                "--policy", "reports/governance_policy.json",
                "--output", "reports/confidence_adaptation.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        # Verify output
        result_path = root / "reports" / "confidence_adaptation.json"
        assert result_path.exists()
        result = json.loads(result_path.read_text(encoding="utf-8"))
        
        assert result["status"] == "ok"
        assert result["confidence_weight"] == 0.9
        assert result["trust_status"] == "High trust"
        # 1.0 * 0.9 = 0.9
        assert result["adjusted_learning_rate"] == 0.9
        
        # Verify policy updated
        updated_policy = json.loads(
            (root / "reports" / "governance_policy.json").read_text(encoding="utf-8")
        )
        assert updated_policy["learning_rate_factor"] == 0.9
        
        # Verify audit marker
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "CONFIDENCE_ADAPTATION:BEGIN" in audit
        assert "High trust" in audit
        assert "lr→0.900" in audit


def test_moderate_confidence_scaling():
    """Test confidence=0.6 scales proportionally (Moderate trust)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_confidence_adaptation_controller.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # Moderate confidence
        confidence_data = {"confidence_weight": 0.6}
        (root / "reports" / "forecast_confidence.json").write_text(
            json.dumps(confidence_data), encoding="utf-8"
        )
        
        policy_data = {"learning_rate_factor": 1.2}
        (root / "reports" / "governance_policy.json").write_text(
            json.dumps(policy_data), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--confidence", "reports/forecast_confidence.json",
                "--policy", "reports/governance_policy.json",
                "--output", "reports/confidence_adaptation.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "confidence_adaptation.json").read_text(encoding="utf-8")
        )
        
        assert result["trust_status"] == "Moderate trust"
        # 1.2 * 0.6 = 0.72
        assert result["adjusted_learning_rate"] == 0.72
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "Moderate trust" in audit


def test_low_confidence_reduction():
    """Test confidence=0.3 reduces learning rate (Low trust)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_confidence_adaptation_controller.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # Low confidence
        confidence_data = {"confidence_weight": 0.3}
        (root / "reports" / "forecast_confidence.json").write_text(
            json.dumps(confidence_data), encoding="utf-8"
        )
        
        policy_data = {"learning_rate_factor": 1.0}
        (root / "reports" / "governance_policy.json").write_text(
            json.dumps(policy_data), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--confidence", "reports/forecast_confidence.json",
                "--policy", "reports/governance_policy.json",
                "--output", "reports/confidence_adaptation.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "confidence_adaptation.json").read_text(encoding="utf-8")
        )
        
        assert result["trust_status"] == "Low trust"
        # 1.0 * 0.3 = 0.3
        assert result["adjusted_learning_rate"] == 0.3
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        assert "Low trust" in audit


def test_clamping_boundaries():
    """Test learning rate clamping to [0.2, 1.5] range."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_confidence_adaptation_controller.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # Very low confidence that would result in rate < 0.2
        confidence_data = {"confidence_weight": 0.1}
        (root / "reports" / "forecast_confidence.json").write_text(
            json.dumps(confidence_data), encoding="utf-8"
        )
        
        policy_data = {"learning_rate_factor": 1.0}
        (root / "reports" / "governance_policy.json").write_text(
            json.dumps(policy_data), encoding="utf-8"
        )
        
        (root / "reports" / "audit_summary.md").write_text(
            "# Audit Summary\n\n", encoding="utf-8"
        )
        
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--confidence", "reports/forecast_confidence.json",
                "--policy", "reports/governance_policy.json",
                "--output", "reports/confidence_adaptation.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "confidence_adaptation.json").read_text(encoding="utf-8")
        )
        
        # 1.0 * 0.1 = 0.1, but clamped to minimum 0.2
        assert result["adjusted_learning_rate"] == 0.2


def test_idempotent_marker_replacement():
    """Test running twice replaces marker instead of duplicating."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_confidence_adaptation_controller.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        confidence_data = {"confidence_weight": 0.85}
        (root / "reports" / "forecast_confidence.json").write_text(
            json.dumps(confidence_data), encoding="utf-8"
        )
        
        policy_data = {"learning_rate_factor": 1.0}
        (root / "reports" / "governance_policy.json").write_text(
            json.dumps(policy_data), encoding="utf-8"
        )
        
        # Pre-existing audit with marker
        initial_audit = """# Audit Summary

<!-- CONFIDENCE_ADAPTATION:BEGIN -->
Old content here
<!-- CONFIDENCE_ADAPTATION:END -->

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
                "--confidence", "reports/forecast_confidence.json",
                "--policy", "reports/governance_policy.json",
                "--output", "reports/confidence_adaptation.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            
            mod.main([
                "--confidence", "reports/forecast_confidence.json",
                "--policy", "reports/governance_policy.json",
                "--output", "reports/confidence_adaptation.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
        finally:
            os.chdir(cwd)
        
        audit = (root / "reports" / "audit_summary.md").read_text(encoding="utf-8")
        
        # Should have exactly one BEGIN and one END marker
        assert audit.count("CONFIDENCE_ADAPTATION:BEGIN") == 1
        assert audit.count("CONFIDENCE_ADAPTATION:END") == 1
        
        # Should not contain old content
        assert "Old content here" not in audit
        
        # Should contain new content
        assert "High trust" in audit
        assert "Other sections remain" in audit


def test_missing_inputs_use_defaults():
    """Test graceful handling when input files are missing."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        scripts_dir = Path.cwd() / "scripts" / "workflow_utils"
        mod = load_module(scripts_dir / "governance_confidence_adaptation_controller.py")
        
        (root / "reports").mkdir(parents=True, exist_ok=True)
        
        # No input files created - should use defaults
        cwd = os.getcwd()
        os.chdir(root)
        try:
            code = mod.main([
                "--confidence", "reports/forecast_confidence.json",
                "--policy", "reports/governance_policy.json",
                "--output", "reports/confidence_adaptation.json",
                "--audit-summary", "reports/audit_summary.md"
            ])
            assert code == 0
        finally:
            os.chdir(cwd)
        
        result = json.loads(
            (root / "reports" / "confidence_adaptation.json").read_text(encoding="utf-8")
        )
        
        # Should use defaults: confidence=1.0, learning_rate=1.0
        assert result["confidence_weight"] == 1.0
        assert result["original_learning_rate"] == 1.0
        # 1.0 * 1.0 = 1.0
        assert result["adjusted_learning_rate"] == 1.0
        assert result["trust_status"] == "High trust"
