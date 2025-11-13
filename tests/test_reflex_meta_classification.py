#!/usr/bin/env python3
"""
test_reflex_meta_classification.py

Test suite for Reflex Meta-Performance classification boundary enforcement.

Ensures that:
- MPI ≥ 80 → "Stable learning"
- 60 ≤ MPI < 80 → "Mild drift"
- MPI < 60 → "Learning degradation"
- Audit marker idempotency maintained
"""

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def cwd(path: str):
    original = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def test_stable_classification_boundary():
    """Test MPI ≥ 80 classified as 'Stable learning'."""
    with tempfile.TemporaryDirectory() as tmpdir, cwd(tmpdir):
        os.makedirs("logs", exist_ok=True)
        os.makedirs("reports", exist_ok=True)
        
        # Create history with strong performance (R² improving)
        history = [
            {"timestamp": "2024-01-01T10:00:00Z", "r2": 0.70, "mae": 0.15},
            {"timestamp": "2024-01-01T11:00:00Z", "r2": 0.85, "mae": 0.12},
        ]
        with open("logs/reflex_model_history.json", "w") as f:
            json.dump(history, f)
        
        # Import and run evaluator
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "workflow_utils"))
        from governance_reflex_meta_evaluator import main
        
        result = main(["--history", "logs/reflex_model_history.json",
                       "--output", "reports/reflex_meta_performance.json",
                       "--audit-summary", "reports/audit_summary.md"])
        
        assert result == 0, "Evaluator should exit cleanly"
        
        # Check output
        with open("reports/reflex_meta_performance.json", "r") as f:
            perf = json.load(f)
        
        mpi = perf["mpi"]
        classification = perf["classification"]
        
        assert mpi >= 80, f"Expected MPI ≥ 80, got {mpi}"
        assert classification == "Stable learning", f"Expected 'Stable learning', got '{classification}'"
        
        # Check audit marker
        with open("reports/audit_summary.md", "r") as f:
            content = f.read()
        
        assert "<!-- REFLEX_META:BEGIN -->" in content
        assert "<!-- REFLEX_META:END -->" in content
        assert "Stable learning" in content


def test_mild_drift_classification_boundary():
    """Test 60 ≤ MPI < 80 classified as 'Mild drift'."""
    with tempfile.TemporaryDirectory() as tmpdir, cwd(tmpdir):
        os.makedirs("logs", exist_ok=True)
        os.makedirs("reports", exist_ok=True)
        
        # Create history with slight degradation
        history = [
            {"timestamp": "2024-01-01T10:00:00Z", "r2": 0.75, "mae": 0.12},
            {"timestamp": "2024-01-01T11:00:00Z", "r2": 0.70, "mae": 0.16},
        ]
        with open("logs/reflex_model_history.json", "w") as f:
            json.dump(history, f)
        
        # Import and run evaluator
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "workflow_utils"))
        from governance_reflex_meta_evaluator import main
        
        result = main(["--history", "logs/reflex_model_history.json",
                       "--output", "reports/reflex_meta_performance.json",
                       "--audit-summary", "reports/audit_summary.md"])
        
        assert result == 0, "Evaluator should exit cleanly"
        
        # Check output
        with open("reports/reflex_meta_performance.json", "r") as f:
            perf = json.load(f)
        
        mpi = perf["mpi"]
        classification = perf["classification"]
        
        assert 60 <= mpi < 80, f"Expected 60 ≤ MPI < 80, got {mpi}"
        assert classification == "Mild drift", f"Expected 'Mild drift', got '{classification}'"


def test_degradation_classification_boundary():
    """Test MPI < 60 classified as 'Learning degradation'."""
    with tempfile.TemporaryDirectory() as tmpdir, cwd(tmpdir):
        os.makedirs("logs", exist_ok=True)
        os.makedirs("reports", exist_ok=True)
        
        # Create history with severe degradation
        history = [
            {"timestamp": "2024-01-01T10:00:00Z", "r2": 0.80, "mae": 0.10},
            {"timestamp": "2024-01-01T11:00:00Z", "r2": 0.30, "mae": 0.40},
        ]
        with open("logs/reflex_model_history.json", "w") as f:
            json.dump(history, f)
        
        # Import and run evaluator
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "workflow_utils"))
        from governance_reflex_meta_evaluator import main
        
        result = main(["--history", "logs/reflex_model_history.json",
                       "--output", "reports/reflex_meta_performance.json",
                       "--audit-summary", "reports/audit_summary.md"])
        
        assert result == 0, "Evaluator should exit cleanly"
        
        # Check output
        with open("reports/reflex_meta_performance.json", "r") as f:
            perf = json.load(f)
        
        mpi = perf["mpi"]
        classification = perf["classification"]
        
        assert mpi < 60, f"Expected MPI < 60, got {mpi}"
        assert classification == "Learning degradation", f"Expected 'Learning degradation', got '{classification}'"


def test_audit_marker_idempotency():
    """Test that running evaluator twice produces single audit marker."""
    with tempfile.TemporaryDirectory() as tmpdir, cwd(tmpdir):
        os.makedirs("logs", exist_ok=True)
        os.makedirs("reports", exist_ok=True)
        
        # Create history
        history = [
            {"timestamp": "2024-01-01T10:00:00Z", "r2": 0.75, "mae": 0.15},
            {"timestamp": "2024-01-01T11:00:00Z", "r2": 0.80, "mae": 0.12},
        ]
        with open("logs/reflex_model_history.json", "w") as f:
            json.dump(history, f)
        
        # Import and run evaluator twice
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "workflow_utils"))
        from governance_reflex_meta_evaluator import main
        
        main(["--history", "logs/reflex_model_history.json",
              "--output", "reports/reflex_meta_performance.json",
              "--audit-summary", "reports/audit_summary.md"])
        
        main(["--history", "logs/reflex_model_history.json",
              "--output", "reports/reflex_meta_performance.json",
              "--audit-summary", "reports/audit_summary.md"])
        
        # Check audit marker appears exactly once
        with open("reports/audit_summary.md", "r") as f:
            content = f.read()
        
        begin_count = content.count("<!-- REFLEX_META:BEGIN -->")
        end_count = content.count("<!-- REFLEX_META:END -->")
        
        assert begin_count == 1, f"Expected 1 BEGIN marker, found {begin_count}"
        assert end_count == 1, f"Expected 1 END marker, found {end_count}"


if __name__ == "__main__":
    test_stable_classification_boundary()
    test_mild_drift_classification_boundary()
    test_degradation_classification_boundary()
    test_audit_marker_idempotency()
    print("✅ All meta-classification tests passed")
