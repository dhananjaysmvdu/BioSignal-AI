#!/usr/bin/env python3
"""
test_meta_feedback_controller.py

Test suite for Governance Meta-Feedback Controller.

Ensures that:
- MPI < 60 (Critical): learning_rate_factor *= 0.8, audit days halved (min 3)
- 60 ≤ MPI < 80 (Caution): learning_rate_factor *= 0.9, audit days * 0.75
- MPI ≥ 80 (Stable): learning_rate_factor *= 1.05 (capped 1.5), audit days unchanged
- Policy persistence: governance_policy.json updated with new parameters
- Audit marker idempotency
"""

import json
import os
import sys
import tempfile
from pathlib import Path


def test_critical_low_mpi():
    """Test MPI=50 (critical) triggers aggressive adjustments."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        os.makedirs("reports", exist_ok=True)
        
        # Create meta-performance with critical MPI
        meta_perf = {
            "status": "ok",
            "mpi": 50.0,
            "classification": "Learning degradation"
        }
        with open("reports/reflex_meta_performance.json", "w") as f:
            json.dump(meta_perf, f)
        
        # Create policy with initial values
        policy = {
            "learning_rate_factor": 1.0,
            "audit_frequency_days": 14
        }
        with open("reports/governance_policy.json", "w") as f:
            json.dump(policy, f)
        
        # Import and run controller
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "workflow_utils"))
        from governance_meta_feedback_controller import main
        
        result = main([
            "--meta-performance", "reports/reflex_meta_performance.json",
            "--policy", "reports/governance_policy.json",
            "--output", "reports/meta_feedback_actions.json",
            "--audit-summary", "reports/audit_summary.md"
        ])
        
        assert result == 0, "Controller should exit cleanly"
        
        # Check output
        with open("reports/meta_feedback_actions.json", "r") as f:
            actions = json.load(f)
        
        assert actions["meta_feedback_status"] == "critical", \
            f"Expected 'critical' status, got '{actions['meta_feedback_status']}'"
        
        # Verify learning rate reduced by 20%
        new_lr = actions["adjustments"]["learning_rate_factor"]["new"]
        assert abs(new_lr - 0.8) < 0.01, \
            f"Expected learning rate ~0.8, got {new_lr}"
        
        # Verify audit frequency halved (14 -> 7)
        new_audit = actions["adjustments"]["audit_frequency_days"]["new"]
        assert new_audit == 7, \
            f"Expected audit frequency 7 days, got {new_audit}"
        
        # Verify policy file updated
        with open("reports/governance_policy.json", "r") as f:
            updated_policy = json.load(f)
        
        assert updated_policy["learning_rate_factor"] == 0.8, \
            "Policy should persist new learning rate"
        assert updated_policy["audit_frequency_days"] == 7, \
            "Policy should persist new audit frequency"
        assert updated_policy["meta_feedback_status"] == "critical", \
            "Policy should include status"
        assert "last_meta_feedback" in updated_policy, \
            "Policy should include timestamp"
        
        # Check audit marker
        with open("reports/audit_summary.md", "r") as f:
            content = f.read()
        
        assert "<!-- META_FEEDBACK:BEGIN -->" in content
        assert "<!-- META_FEEDBACK:END -->" in content
        assert "critical" in content


def test_caution_mid_mpi():
    """Test MPI=70 (caution) triggers moderate adjustments."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        os.makedirs("reports", exist_ok=True)
        
        # Create meta-performance with caution MPI
        meta_perf = {
            "status": "ok",
            "mpi": 70.0,
            "classification": "Mild drift"
        }
        with open("reports/reflex_meta_performance.json", "w") as f:
            json.dump(meta_perf, f)
        
        # Create policy with initial values
        policy = {
            "learning_rate_factor": 1.0,
            "audit_frequency_days": 12
        }
        with open("reports/governance_policy.json", "w") as f:
            json.dump(policy, f)
        
        # Import and run controller
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "workflow_utils"))
        from governance_meta_feedback_controller import main
        
        result = main([
            "--meta-performance", "reports/reflex_meta_performance.json",
            "--policy", "reports/governance_policy.json",
            "--output", "reports/meta_feedback_actions.json",
            "--audit-summary", "reports/audit_summary.md"
        ])
        
        assert result == 0, "Controller should exit cleanly"
        
        # Check output
        with open("reports/meta_feedback_actions.json", "r") as f:
            actions = json.load(f)
        
        assert actions["meta_feedback_status"] == "caution", \
            f"Expected 'caution' status, got '{actions['meta_feedback_status']}'"
        
        # Verify learning rate reduced by 10%
        new_lr = actions["adjustments"]["learning_rate_factor"]["new"]
        assert abs(new_lr - 0.9) < 0.01, \
            f"Expected learning rate ~0.9, got {new_lr}"
        
        # Verify audit frequency increased by 25% (12 -> 9)
        new_audit = actions["adjustments"]["audit_frequency_days"]["new"]
        assert new_audit == 9, \
            f"Expected audit frequency 9 days, got {new_audit}"
        
        # Verify policy persistence
        with open("reports/governance_policy.json", "r") as f:
            updated_policy = json.load(f)
        
        assert updated_policy["learning_rate_factor"] == 0.9
        assert updated_policy["audit_frequency_days"] == 9
        assert updated_policy["meta_feedback_status"] == "caution"


def test_stable_high_mpi():
    """Test MPI=90 (stable) increases learning rate with cap."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        os.makedirs("reports", exist_ok=True)
        
        # Create meta-performance with stable MPI
        meta_perf = {
            "status": "ok",
            "mpi": 90.0,
            "classification": "Stable learning"
        }
        with open("reports/reflex_meta_performance.json", "w") as f:
            json.dump(meta_perf, f)
        
        # Create policy with initial values
        policy = {
            "learning_rate_factor": 1.0,
            "audit_frequency_days": 14
        }
        with open("reports/governance_policy.json", "w") as f:
            json.dump(policy, f)
        
        # Import and run controller
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "workflow_utils"))
        from governance_meta_feedback_controller import main
        
        result = main([
            "--meta-performance", "reports/reflex_meta_performance.json",
            "--policy", "reports/governance_policy.json",
            "--output", "reports/meta_feedback_actions.json",
            "--audit-summary", "reports/audit_summary.md"
        ])
        
        assert result == 0, "Controller should exit cleanly"
        
        # Check output
        with open("reports/meta_feedback_actions.json", "r") as f:
            actions = json.load(f)
        
        assert actions["meta_feedback_status"] == "stable", \
            f"Expected 'stable' status, got '{actions['meta_feedback_status']}'"
        
        # Verify learning rate increased by 5%
        new_lr = actions["adjustments"]["learning_rate_factor"]["new"]
        assert abs(new_lr - 1.05) < 0.01, \
            f"Expected learning rate ~1.05, got {new_lr}"
        
        # Verify audit frequency unchanged
        new_audit = actions["adjustments"]["audit_frequency_days"]["new"]
        assert new_audit == 14, \
            f"Expected audit frequency 14 days, got {new_audit}"
        
        # Verify cap enforcement (test with high initial lr)
        policy_high = {
            "learning_rate_factor": 1.45,
            "audit_frequency_days": 14
        }
        with open("reports/governance_policy.json", "w") as f:
            json.dump(policy_high, f)
        
        result2 = main([
            "--meta-performance", "reports/reflex_meta_performance.json",
            "--policy", "reports/governance_policy.json",
            "--output", "reports/meta_feedback_actions.json",
            "--audit-summary", "reports/audit_summary.md"
        ])
        
        with open("reports/meta_feedback_actions.json", "r") as f:
            actions2 = json.load(f)
        
        capped_lr = actions2["adjustments"]["learning_rate_factor"]["new"]
        assert capped_lr <= 1.5, \
            f"Learning rate should be capped at 1.5, got {capped_lr}"


def test_audit_marker_idempotency():
    """Test that running controller twice produces single audit marker."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        os.makedirs("reports", exist_ok=True)
        
        # Create meta-performance
        meta_perf = {
            "status": "ok",
            "mpi": 85.0,
            "classification": "Stable learning"
        }
        with open("reports/reflex_meta_performance.json", "w") as f:
            json.dump(meta_perf, f)
        
        # Create policy
        policy = {
            "learning_rate_factor": 1.0,
            "audit_frequency_days": 14
        }
        with open("reports/governance_policy.json", "w") as f:
            json.dump(policy, f)
        
        # Import and run controller twice
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "workflow_utils"))
        from governance_meta_feedback_controller import main
        
        main([
            "--meta-performance", "reports/reflex_meta_performance.json",
            "--policy", "reports/governance_policy.json",
            "--output", "reports/meta_feedback_actions.json",
            "--audit-summary", "reports/audit_summary.md"
        ])
        
        main([
            "--meta-performance", "reports/reflex_meta_performance.json",
            "--policy", "reports/governance_policy.json",
            "--output", "reports/meta_feedback_actions.json",
            "--audit-summary", "reports/audit_summary.md"
        ])
        
        # Check audit marker appears exactly once
        with open("reports/audit_summary.md", "r") as f:
            content = f.read()
        
        begin_count = content.count("<!-- META_FEEDBACK:BEGIN -->")
        end_count = content.count("<!-- META_FEEDBACK:END -->")
        
        assert begin_count == 1, f"Expected 1 BEGIN marker, found {begin_count}"
        assert end_count == 1, f"Expected 1 END marker, found {end_count}"


if __name__ == "__main__":
    test_critical_low_mpi()
    test_caution_mid_mpi()
    test_stable_high_mpi()
    test_audit_marker_idempotency()
    print("✅ All meta-feedback controller tests passed")
