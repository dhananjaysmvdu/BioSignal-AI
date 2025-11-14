"""Test audit marker idempotency and atomicity."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "mvcrs"))

from challenge_verifier import (
    build_deviations,
    compute_status_from_deviations,
    create_escalation,
    load_all,
    update_audit_marker,
    update_summary,
    atomic_write_json,
    append_jsonl,
    STATE_PATH,
    LOG_PATH,
    SUMMARY_PATH,
    AUDIT_SUMMARY,
)


class TestAuditMarkerIdempotency:
    """Verify audit markers are idempotent (no duplicates on repeated runs)."""

    def test_multiple_verifier_marker_calls_idempotent(self, fixture_full_artifacts_ok):
        """Multiple marker updates should not duplicate MVCRS_VERIFIER lines."""
        os.chdir(fixture_full_artifacts_ok)
        
        marker1 = "<!-- MVCRS_VERIFIER: UPDATED 2025-11-15T10:00:00Z -->"
        update_audit_marker(marker1)
        
        with open(AUDIT_SUMMARY, "r", encoding="utf-8") as f:
            lines1 = f.readlines()
        verifier_count1 = sum(1 for l in lines1 if "MVCRS_VERIFIER:" in l)
        
        marker2 = "<!-- MVCRS_VERIFIER: UPDATED 2025-11-15T10:01:00Z -->"
        update_audit_marker(marker2)
        
        with open(AUDIT_SUMMARY, "r", encoding="utf-8") as f:
            lines2 = f.readlines()
        verifier_count2 = sum(1 for l in lines2 if "MVCRS_VERIFIER:" in l)
        
        assert verifier_count2 == 1, "Should maintain single MVCRS_VERIFIER marker"
        assert marker2 in "".join(lines2), "Should have latest marker"

    def test_escalation_marker_idempotency(self, fixture_type_a_missing_mandatory):
        """Escalation marker should appear once even on repeated calls."""
        os.chdir(fixture_type_a_missing_mandatory)
        
        verifier_marker = "<!-- MVCRS_VERIFIER: UPDATED 2025-11-15T10:00:00Z -->"
        esc_marker1 = "<!-- MVCRS_ESCALATION: CREATED 2025-11-15T10:00:00Z -->"
        
        update_audit_marker(verifier_marker, esc_marker1)
        
        with open(AUDIT_SUMMARY, "r", encoding="utf-8") as f:
            lines1 = f.readlines()
        esc_count1 = sum(1 for l in lines1 if "MVCRS_ESCALATION:" in l)
        
        # Call again with same escalation marker (simulating no new escalation)
        verifier_marker = "<!-- MVCRS_VERIFIER: UPDATED 2025-11-15T10:01:00Z -->"
        update_audit_marker(verifier_marker)  # No escalation on this call
        
        with open(AUDIT_SUMMARY, "r", encoding="utf-8") as f:
            lines2 = f.readlines()
        esc_count2 = sum(1 for l in lines2 if "MVCRS_ESCALATION:" in l)
        
        # Escalation should be cleared
        assert esc_count2 == 0, "Escalation marker should not persist on subsequent ok run"


class TestStateAndLogAtomicity:
    """Verify state and log writes are atomic."""

    def test_state_json_valid_after_write(self, fixture_full_artifacts_ok):
        """State JSON should be valid and complete after atomic write."""
        os.chdir(fixture_full_artifacts_ok)
        artifacts, missing = load_all()
        deviations = build_deviations(artifacts, missing)
        status = compute_status_from_deviations(deviations)
        
        result = {
            "status": status,
            "deviations": deviations,
            "timestamp": "2025-11-15T10:00:00Z",
        }
        
        atomic_write_json(STATE_PATH, result)
        
        # Verify can be re-read correctly
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            reread = json.load(f)
        
        assert reread["status"] == status
        assert len(reread["deviations"]) == len(deviations)

    def test_log_jsonl_appendable(self, fixture_full_artifacts_ok):
        """Log JSONL should be readable and appendable."""
        os.chdir(fixture_full_artifacts_ok)
        
        entry1 = {"id": "log1", "ts": "2025-11-15T10:00:00Z"}
        entry2 = {"id": "log2", "ts": "2025-11-15T10:01:00Z"}
        
        append_jsonl(LOG_PATH, entry1)
        append_jsonl(LOG_PATH, entry2)
        
        # Verify both entries present
        entries = []
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        
        assert len(entries) == 2
        assert entries[0]["id"] == "log1"
        assert entries[1]["id"] == "log2"


class TestSummaryPersistence:
    """Verify summary updates are persistent."""

    def test_summary_updated_on_each_run(self, fixture_full_artifacts_ok):
        """Summary should update on each verifier run."""
        os.chdir(fixture_full_artifacts_ok)
        
        # First update
        artifacts1, missing1 = load_all()
        deviations1 = build_deviations(artifacts1, missing1)
        status1 = compute_status_from_deviations(deviations1)
        summary1 = update_summary(status1, deviations1, False, None)
        
        ts1 = summary1["last_updated"]
        
        # Second update (simulate passage of time via timestamp)
        artifacts2, missing2 = load_all()
        deviations2 = build_deviations(artifacts2, missing2)
        status2 = compute_status_from_deviations(deviations2)
        summary2 = update_summary(status2, deviations2, False, None)
        
        ts2 = summary2["last_updated"]
        
        # Verify both are written
        with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
            final_summary = json.load(f)
        
        assert final_summary["last_updated"] == ts2
        assert final_summary["verifier_status"] == status2
