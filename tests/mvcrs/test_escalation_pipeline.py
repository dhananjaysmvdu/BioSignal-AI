"""Test escalation artifact creation and integrity."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "mvcrs"))

from challenge_verifier import (
    build_deviations,
    create_escalation,
    load_all,
)


class TestEscalationArtifactCreation:
    """Verify escalation artifact is created when high-severity deviations exist."""

    def test_escalation_created_on_missing_mandatory(self, fixture_type_a_missing_mandatory):
        """Escalation artifact should be created for high-severity TYPE_A."""
        os.chdir(fixture_type_a_missing_mandatory)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        
        high_devs = [d for d in deviations if d["severity"] == "high"]
        assert len(high_devs) > 0
        
        escalation = create_escalation(deviations, artifacts)
        
        assert escalation is not None
        assert "id" in escalation
        assert "timestamp" in escalation
        assert "recommended_action" in escalation
        assert "high_severity_deviations" in escalation
        assert len(escalation["high_severity_deviations"]) > 0

    def test_escalation_not_created_for_medium_only(self, fixture_type_b_low_consensus):
        """Escalation should not be created for medium-only deviations."""
        os.chdir(fixture_type_b_low_consensus)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        
        high_devs = [d for d in deviations if d["severity"] == "high"]
        assert len(high_devs) == 0, "Test fixture should have no high-severity deviations"


class TestEscalationRecommendedActions:
    """Verify escalation recommended_action matches deviation type."""

    def test_type_a_recommends_self_healing(self, fixture_type_a_missing_mandatory):
        """TYPE_A structural deviations should recommend trigger_self_healing."""
        os.chdir(fixture_type_a_missing_mandatory)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        
        escalation = create_escalation(deviations, artifacts)
        assert escalation["recommended_action"] == "trigger_self_healing"

    def test_type_b_recommends_threshold_recompute(self, fixture_type_b_rdgl_locked_non_red_policy):
        """TYPE_B consistency deviations with high severity recommend force_threshold_recompute."""
        os.chdir(fixture_type_b_rdgl_locked_non_red_policy)
        
        # Manually add a high-severity TYPE_B for testing
        artifacts = {
            "state/challenge_events.jsonl": {"exists": True},
            "state/challenges_chain_meta.json": {"exists": True},
            "state/rdgl_policy_adjustments.json": {"mode": "locked"},
            "state/policy_fusion_state.json": {
                "inputs": {"policy": "GREEN", "weighted_consensus_pct": 95}
            },
        }
        deviations = [
            {
                "type": "TYPE_B_CONSISTENCY",
                "severity": "high",
                "metric": "test",
            }
        ]
        
        escalation = create_escalation(deviations, artifacts)
        assert escalation["recommended_action"] == "force_threshold_recompute"


class TestMixedEscalation:
    """Test escalation with multiple deviation types."""

    def test_mixed_high_severity_a_and_b(self, fixture_multiple_high_severity_a_and_b):
        """Mixed high-severity deviations should all be included in escalation."""
        os.chdir(fixture_multiple_high_severity_a_and_b)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        
        high_devs = [d for d in deviations if d["severity"] == "high"]
        assert len(high_devs) > 0, "Should have high-severity deviations"
        
        escalation = create_escalation(deviations, artifacts)
        
        assert len(escalation["high_severity_deviations"]) > 0
        high_devs_in_escalation = escalation["high_severity_deviations"]
        
        # Should include the missing mandatory and promoted TYPE_B
        types_in_escalation = {d["type"] for d in high_devs_in_escalation}
        assert "TYPE_A_STRUCTURE" in types_in_escalation or "TYPE_B_CONSISTENCY" in types_in_escalation
