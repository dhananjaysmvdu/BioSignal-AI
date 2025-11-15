#!/usr/bin/env python3
"""Tests for human approval API."""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from supervision import human_approval_api as api


@pytest.fixture
def temp_state(tmp_path, monkeypatch):
    """Create temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    
    monkeypatch.setattr(api, "STATE_DIR", state_dir)
    monkeypatch.setattr(api, "APPROVAL_STATE", state_dir / "approval_state.json")
    monkeypatch.setattr(api, "APPROVAL_REQUESTS", state_dir / "approval_requests.jsonl")
    monkeypatch.setattr(api, "APPROVAL_HIGHWATER", state_dir / "approval_highwater.json")
    
    return state_dir


def test_get_status_default(temp_state):
    """Test get_status returns default when no state exists."""
    status = api.get_status()
    assert status["status"] == "unlocked"
    assert status["approval_id"] is None
    assert "last_updated" in status


def test_request_approval_creates_record(temp_state):
    """Test request_approval creates UUID and writes to JSONL."""
    result = api.request_approval("alice", "Testing approval flow")
    
    assert "approval_id" in result
    assert result["status"] == "requested"
    assert api.APPROVAL_REQUESTS.exists()
    
    # Check JSONL content
    lines = [ln for ln in api.APPROVAL_REQUESTS.read_text().splitlines() if ln.strip() and not ln.startswith("<!--")]
    assert len(lines) == 1
    
    record = json.loads(lines[0])
    assert record["approval_id"] == result["approval_id"]
    assert record["requester"] == "alice"
    assert record["status"] == "requested"


def test_request_approval_updates_state(temp_state):
    """Test request_approval updates approval_state.json."""
    result = api.request_approval("bob", "Emergency override")
    
    assert api.APPROVAL_STATE.exists()
    state = json.loads(api.APPROVAL_STATE.read_text())
    
    assert state["status"] == "pending_approval"
    assert state["approval_id"] == result["approval_id"]


def test_grant_approval_valid(temp_state, monkeypatch):
    """Test grant_approval succeeds for valid request."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    # Create request
    result = api.request_approval("charlie", "Deploy production")
    approval_id = result["approval_id"]
    
    # Grant
    grant_result = api.grant_approval(approval_id, "dave")
    
    assert grant_result["status"] == "granted"
    assert grant_result["approver"] == "dave"
    assert "signature" in grant_result
    
    # Verify JSONL updated
    lines = [ln for ln in api.APPROVAL_REQUESTS.read_text().splitlines() if ln.strip() and not ln.startswith("<!--")]
    record = json.loads(lines[0])
    
    assert record["status"] == "granted"
    assert record["approver"] == "dave"
    assert record["signature_meta"]["method"] == "hmac-sha256"


def test_grant_approval_missing_id(temp_state):
    """Test grant_approval fails for non-existent ID."""
    result = api.grant_approval(str(uuid.uuid4()), "eve")
    
    assert "error" in result
    assert ("not found" in result["error"].lower() or "no approval" in result["error"].lower())


def test_grant_approval_already_granted(temp_state, monkeypatch):
    """Test grant_approval fails if already granted."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    result = api.request_approval("frank", "Test")
    approval_id = result["approval_id"]
    
    # Grant once
    api.grant_approval(approval_id, "grace")
    
    # Try again
    result2 = api.grant_approval(approval_id, "heidi")
    
    assert "error" in result2
    assert "already granted" in result2["error"].lower()


def test_daily_limit_enforcement(temp_state, monkeypatch):
    """Test check_daily_limit enforces 5/day default."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    approver = "ivan"
    
    # Grant 5 approvals
    for i in range(5):
        result = api.request_approval(f"requester{i}", f"Reason {i}")
        api.grant_approval(result["approval_id"], approver)
    
    # 6th should fail
    result6 = api.request_approval("requester6", "Reason 6")
    grant_result = api.grant_approval(result6["approval_id"], approver)
    
    assert "error" in grant_result
    assert "limit" in grant_result["error"].lower()
    assert grant_result.get("http_code") == 403


def test_override_approval_valid_key(temp_state, monkeypatch):
    """Test override_approval succeeds with valid key."""
    monkeypatch.setenv("OVERRIDE_KEY", "secret-override-key")
    
    approval_id = str(uuid.uuid4())
    result = api.override_approval("secret-override-key", approval_id, "judy", "Emergency")
    
    assert result["status"] == "granted"
    assert result["approver"] == "OVERRIDE"
    
    # Verify JSONL
    lines = [ln for ln in api.APPROVAL_REQUESTS.read_text().splitlines() if ln.strip() and not ln.startswith("<!--")]
    record = json.loads(lines[0])
    
    assert record["status"] == "granted"
    assert record["signature_meta"]["method"] == "override"


def test_override_approval_invalid_key(temp_state, monkeypatch):
    """Test override_approval fails with invalid key."""
    monkeypatch.setenv("OVERRIDE_KEY", "correct-key")
    
    result = api.override_approval("wrong-key", str(uuid.uuid4()), "kevin", "Emergency")
    
    assert "error" in result
    assert result.get("http_code") == 403


def test_atomic_write_retries(temp_state, monkeypatch):
    """Test atomic_write_json retries on failure."""
    fail_count = 0
    original_write = Path.write_text
    
    def failing_write(self, *args, **kwargs):
        nonlocal fail_count
        fail_count += 1
        if fail_count < 3:
            raise OSError("Simulated write failure")
        return original_write(self, *args, **kwargs)
    
    monkeypatch.setattr(Path, "write_text", failing_write)
    
    data = {"test": "data"}
    test_file = temp_state / "test.json"
    
    api.atomic_write_json(test_file, data, retries=3)
    
    assert test_file.exists()
    assert fail_count == 3  # Failed twice, succeeded third time


def test_atomic_write_creates_fix_branch(temp_state, monkeypatch):
    """Test atomic_write_json creates fix branch on persistent failure."""
    fix_branch_called = []
    
    def mock_create_fix_branch(path, error):
        fix_branch_called.append((path, str(error)))
    
    monkeypatch.setattr(api, "create_fix_branch", mock_create_fix_branch)
    
    # Mock Path.write_text to always fail
    def always_fail(*args, **kwargs):
        raise OSError("Persistent failure")
    
    monkeypatch.setattr(Path, "write_text", always_fail)
    
    data = {"test": "data"}
    test_file = temp_state / "test.json"
    
    with pytest.raises(OSError, match="Persistent failure"):
        api.atomic_write_json(test_file, data, retries=3)
    
    # Verify fix branch creation was called
    assert len(fix_branch_called) == 1, "Fix branch creation should be called once"
    called_path, called_error = fix_branch_called[0]
    assert str(test_file) in str(called_path), f"Expected path containing {test_file}, got {called_path}"
    assert "Persistent failure" in called_error


def test_audit_marker_idempotent(temp_state):
    """Test append_audit_marker is idempotent."""
    api.request_approval("laura", "Test")
    
    initial_content = api.APPROVAL_REQUESTS.read_text()
    marker_count_before = initial_content.count("<!-- HUMAN_APPROVAL:")
    
    # Append marker manually
    api.append_audit_marker("<!-- HUMAN_APPROVAL: TEST1 2025-01-01T00:00:00+00:00 -->")
    
    content_after_1 = api.APPROVAL_REQUESTS.read_text()
    marker_count_1 = content_after_1.count("<!-- HUMAN_APPROVAL:")
    
    # Should have same count (marker replaced)
    assert marker_count_1 == marker_count_before
    assert "TEST1" in content_after_1
    
    # Append another marker - should replace previous
    api.append_audit_marker("<!-- HUMAN_APPROVAL: TEST2 2025-01-01T00:01:00+00:00 -->")
    
    content_after_2 = api.APPROVAL_REQUESTS.read_text()
    marker_count_2 = content_after_2.count("<!-- HUMAN_APPROVAL:")
    
    assert marker_count_2 == marker_count_before  # Still same count
    assert "TEST2" in content_after_2
    assert "TEST1" not in content_after_2


def test_signature_included_in_grant(temp_state, monkeypatch):
    """Test grant_approval includes signature metadata."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    result = api.request_approval("mike", "Test signature")
    grant = api.grant_approval(result["approval_id"], "nancy")
    
    assert "signature" in grant
    assert grant["signature"]  # Non-empty
    
    # Verify in JSONL
    lines = [ln for ln in api.APPROVAL_REQUESTS.read_text().splitlines() if ln.strip() and not ln.startswith("<!--")]
    record = json.loads(lines[0])
    
    sig_meta = record["signature_meta"]
    assert sig_meta["method"] == "hmac-sha256"
    assert sig_meta["signature"]
    assert sig_meta["signed_hash"]
    assert sig_meta["approver"] == "nancy"
