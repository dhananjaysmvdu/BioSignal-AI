"""Test isolation of each deviation type (TYPE_A through TYPE_D)."""

import json
import os
import sys
from pathlib import Path

import pytest

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "mvcrs"))

from challenge_verifier import (
    build_deviations,
    compute_status_from_deviations,
    load_all,
)


class TestTypeAStructure:
    """TYPE_A_STRUCTURE: missing/corrupt artifacts."""

    def test_missing_mandatory_file_high_severity(self, fixture_type_a_missing_mandatory):
        """Missing mandatory file should produce high-severity TYPE_A deviation."""
        os.chdir(fixture_type_a_missing_mandatory)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)

        type_a_devs = [d for d in deviations if d["type"] == "TYPE_A_STRUCTURE"]
        assert len(type_a_devs) > 0, "Should have TYPE_A deviation for missing mandatory"
        
        high_severity_a = [d for d in type_a_devs if d["severity"] == "high"]
        assert len(high_severity_a) > 0, "Missing mandatory should be high severity"
        
        assert any("state/challenge_events.jsonl" in str(d) for d in high_severity_a)

    def test_corrupt_jsonl_high_severity(self, fixture_type_a_corrupt_jsonl):
        """Corrupt JSONL should produce high-severity TYPE_A deviation."""
        os.chdir(fixture_type_a_corrupt_jsonl)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)

        type_a_devs = [d for d in deviations if d["type"] == "TYPE_A_STRUCTURE"]
        high_severity_a = [d for d in type_a_devs if d["severity"] == "high"]
        
        assert len(high_severity_a) > 0, "Corrupt JSONL should produce high-severity TYPE_A"
        assert any("parse_error" in str(d) for d in high_severity_a)


class TestTypeBConsistency:
    """TYPE_B_CONSISTENCY: policy/consensus/RDGL mismatches."""

    def test_rdgl_locked_non_red_policy(self, fixture_type_b_rdgl_locked_non_red_policy):
        """RDGL locked but policy not RED should produce TYPE_B medium deviation."""
        os.chdir(fixture_type_b_rdgl_locked_non_red_policy)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)

        type_b_devs = [d for d in deviations if d["type"] == "TYPE_B_CONSISTENCY"]
        assert len(type_b_devs) > 0, "Should detect RDGL/policy mismatch"
        
        medium_b = [d for d in type_b_devs if d["severity"] == "medium"]
        assert len(medium_b) > 0, "RDGL/policy mismatch should be medium severity"

    def test_low_consensus(self, fixture_type_b_low_consensus):
        """Consensus <90% should produce TYPE_B medium deviation."""
        os.chdir(fixture_type_b_low_consensus)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)

        type_b_devs = [d for d in deviations if d["type"] == "TYPE_B_CONSISTENCY"]
        assert len(type_b_devs) > 0, "Should detect low consensus"
        
        medium_b = [d for d in type_b_devs if d["severity"] == "medium"]
        assert len(medium_b) > 0, "Low consensus should be medium severity"


class TestTypeCForecast:
    """TYPE_C_FORECAST: risk vs response mismatches."""

    def test_high_risk_low_responses(self, fixture_type_c_high_risk_low_responses):
        """High risk with <2 responses should produce TYPE_C medium deviation."""
        os.chdir(fixture_type_c_high_risk_low_responses)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)

        type_c_devs = [d for d in deviations if d["type"] == "TYPE_C_FORECAST"]
        assert len(type_c_devs) > 0, "Should detect high risk with low responses"
        
        medium_c = [d for d in type_c_devs if d["severity"] == "medium"]
        assert len(medium_c) > 0, "High risk low responses should be medium severity"

    def test_low_risk_high_responses(self, fixture_type_c_low_risk_high_responses):
        """Low risk with >5 responses should produce TYPE_C medium deviation."""
        os.chdir(fixture_type_c_low_risk_high_responses)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)

        type_c_devs = [d for d in deviations if d["type"] == "TYPE_C_FORECAST"]
        assert len(type_c_devs) > 0, "Should detect low risk with high responses"
        
        medium_c = [d for d in type_c_devs if d["severity"] == "medium"]
        assert len(medium_c) > 0, "Low risk high responses should be medium severity"


class TestTypeDUnexpectedAction:
    """TYPE_D_UNEXPECTED_ACTION: actions during trust lock."""

    def test_adaptive_response_under_trust_lock_medium_severity(
        self, fixture_type_d_adaptive_response_under_trust_lock
    ):
        """Adaptive response while trust_lock=True should produce TYPE_D medium deviation."""
        os.chdir(fixture_type_d_adaptive_response_under_trust_lock)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)

        type_d_devs = [d for d in deviations if d["type"] == "TYPE_D_UNEXPECTED_ACTION"]
        assert len(type_d_devs) > 0, "Should detect adaptive response under trust lock"
        
        medium_d = [d for d in type_d_devs if d["severity"] == "medium"]
        assert len(medium_d) > 0, "TYPE_D should be medium severity (per spec)"


class TestStatusFromDeviations:
    """Verify status computation rules."""

    def test_status_failed_with_high_severity(self, fixture_type_a_missing_mandatory):
        """Any high-severity deviation should produce status=failed."""
        os.chdir(fixture_type_a_missing_mandatory)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        
        status = compute_status_from_deviations(deviations)
        assert status == "failed", "High-severity deviation should result in failed status"

    def test_status_warning_with_medium_severity(
        self, fixture_type_b_low_consensus
    ):
        """Any medium-severity deviation (no high) should produce status=warning."""
        os.chdir(fixture_type_b_low_consensus)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        
        status = compute_status_from_deviations(deviations)
        assert status == "warning", "Medium-only deviations should result in warning status"

    def test_status_ok_with_only_low_severity(self, fixture_full_artifacts_ok):
        """Only low-severity deviations should produce status=ok."""
        os.chdir(fixture_full_artifacts_ok)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        
        status = compute_status_from_deviations(deviations)
        assert status == "ok", "Low-only deviations should result in ok status"
