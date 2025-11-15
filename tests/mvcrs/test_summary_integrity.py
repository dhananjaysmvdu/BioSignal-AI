"""Test summary generation and integrity."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "mvcrs"))

from challenge_verifier import (
    build_deviations,
    compute_status_from_deviations,
    load_all,
    update_summary,
    DEVIATION_TYPES,
)


class TestSummaryStructure:
    """Verify summary has correct structure and fields."""

    def test_summary_has_required_fields(self, fixture_full_artifacts_ok):
        """Summary should have all required fields."""
        os.chdir(fixture_full_artifacts_ok)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        status = compute_status_from_deviations(deviations)
        
        summary = update_summary(status, deviations, False, None)
        
        assert "total_events" in summary
        assert "recent_window_events" in summary
        assert "deviation_counts" in summary
        assert "severity_totals" in summary
        assert "verifier_status" in summary
        assert "escalation_triggered" in summary
        assert "last_escalation_ts" in summary
        assert "last_updated" in summary

    def test_deviation_counts_structure(self, fixture_full_artifacts_ok):
        """Deviation counts should have all types with severity breakdown."""
        os.chdir(fixture_full_artifacts_ok)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        status = compute_status_from_deviations(deviations)
        
        summary = update_summary(status, deviations, False, None)
        dev_counts = summary["deviation_counts"]
        
        # Should have all deviation types
        for dtype in DEVIATION_TYPES:
            assert dtype in dev_counts, f"Missing {dtype} in deviation_counts"
            assert "low" in dev_counts[dtype]
            assert "medium" in dev_counts[dtype]
            assert "high" in dev_counts[dtype]

    def test_severity_totals_match_deviations(self, fixture_type_b_low_consensus):
        """Severity totals should sum correctly from deviations."""
        os.chdir(fixture_type_b_low_consensus)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        status = compute_status_from_deviations(deviations)
        
        summary = update_summary(status, deviations, False, None)
        
        # Manually compute expected totals
        expected_low = sum(1 for d in deviations if d["severity"] == "low")
        expected_medium = sum(1 for d in deviations if d["severity"] == "medium")
        expected_high = sum(1 for d in deviations if d["severity"] == "high")
        
        assert summary["severity_totals"]["low"] == expected_low
        assert summary["severity_totals"]["medium"] == expected_medium
        assert summary["severity_totals"]["high"] == expected_high


class TestSummaryDevCountAccuracy:
    """Verify deviation count accuracy per type and severity."""

    def test_type_a_counts_accurate(self, fixture_type_a_corrupt_jsonl):
        """TYPE_A deviation counts should be accurate."""
        os.chdir(fixture_type_a_corrupt_jsonl)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        status = compute_status_from_deviations(deviations)
        
        summary = update_summary(status, deviations, False, None)
        type_a_count = summary["deviation_counts"]["TYPE_A_STRUCTURE"]
        
        # Count from actual deviations
        actual_type_a = [d for d in deviations if d["type"] == "TYPE_A_STRUCTURE"]
        actual_high = sum(1 for d in actual_type_a if d["severity"] == "high")
        actual_medium = sum(1 for d in actual_type_a if d["severity"] == "medium")
        actual_low = sum(1 for d in actual_type_a if d["severity"] == "low")
        
        assert type_a_count["high"] == actual_high
        assert type_a_count["medium"] == actual_medium
        assert type_a_count["low"] == actual_low

    def test_type_b_counts_accurate(self, fixture_type_b_low_consensus):
        """TYPE_B deviation counts should be accurate."""
        os.chdir(fixture_type_b_low_consensus)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        status = compute_status_from_deviations(deviations)
        
        summary = update_summary(status, deviations, False, None)
        type_b_count = summary["deviation_counts"]["TYPE_B_CONSISTENCY"]
        
        actual_type_b = [d for d in deviations if d["type"] == "TYPE_B_CONSISTENCY"]
        actual_high = sum(1 for d in actual_type_b if d["severity"] == "high")
        actual_medium = sum(1 for d in actual_type_b if d["severity"] == "medium")
        actual_low = sum(1 for d in actual_type_b if d["severity"] == "low")
        
        assert type_b_count["high"] == actual_high
        assert type_b_count["medium"] == actual_medium
        assert type_b_count["low"] == actual_low


class TestSummaryEscalationFlag:
    """Verify escalation trigger flags in summary."""

    def test_escalation_flag_true_on_failure(self, fixture_type_a_missing_mandatory):
        """Escalation flag should be True when status would be failed."""
        os.chdir(fixture_type_a_missing_mandatory)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        
        summary = update_summary("failed", deviations, True, "2025-11-15T10:00:00Z")
        
        assert summary["escalation_triggered"] is True
        assert summary["last_escalation_ts"] == "2025-11-15T10:00:00Z"

    def test_escalation_flag_false_on_ok(self, fixture_full_artifacts_ok):
        """Escalation flag should be False when status is ok."""
        os.chdir(fixture_full_artifacts_ok)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        status = compute_status_from_deviations(deviations)
        
        summary = update_summary(status, deviations, False, None)
        
        assert summary["escalation_triggered"] is False
        assert summary["last_escalation_ts"] is None
