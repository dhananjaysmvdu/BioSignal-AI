#!/usr/bin/env python3
"""Tests for verify_approval script."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from supervision import verify_approval as verifier


@pytest.fixture
def temp_state(tmp_path, monkeypatch):
    """Create temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    
    requests_file = state_dir / "approval_requests.jsonl"
    monkeypatch.setattr(verifier, "APPROVAL_REQUESTS", requests_file)
    
    return requests_file


def test_verify_approval_granted_valid(temp_state, monkeypatch):
    """Test verify_approval succeeds for valid granted approval."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    approval_id = "test-uuid-1234"
    timestamp = datetime.now(timezone.utc).isoformat()
    grant_timestamp = datetime.now(timezone.utc).isoformat()
    
    # Create canonical payload and sign
    from supervision.signature_utils import canonical_payload, sign_payload
    
    payload = canonical_payload(approval_id, "alice", "Test reason", timestamp, "granted")
    sig_meta = sign_payload(payload)
    sig_meta["approver"] = "bob"
    sig_meta["grant_timestamp"] = grant_timestamp
    
    record = {
        "approval_id": approval_id,
        "requester": "alice",
        "reason": "Test reason",
        "timestamp": timestamp,
        "status": "granted",
        "approver": "bob",
        "signature_meta": sig_meta,
        "grant_timestamp": grant_timestamp
    }
    
    temp_state.write_text(json.dumps(record) + "\n")
    
    valid, message = verifier.verify_approval(approval_id, ttl_hours=72)
    
    assert valid
    assert "Valid" in message


def test_verify_approval_not_found(temp_state):
    """Test verify_approval fails for missing ID."""
    temp_state.write_text("")
    
    valid, message = verifier.verify_approval("nonexistent-id")
    
    assert not valid
    assert ("not found" in message.lower() or "no approval" in message.lower())


def test_verify_approval_not_granted(temp_state):
    """Test verify_approval fails for non-granted status."""
    approval_id = "test-uuid-5678"
    
    record = {
        "approval_id": approval_id,
        "requester": "charlie",
        "reason": "Pending",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "requested",
        "approver": None,
        "signature_meta": None
    }
    
    temp_state.write_text(json.dumps(record) + "\n")
    
    valid, message = verifier.verify_approval(approval_id)
    
    assert not valid
    assert "requested" in message


def test_verify_approval_no_signature(temp_state):
    """Test verify_approval fails when signature missing."""
    approval_id = "test-uuid-9012"
    
    record = {
        "approval_id": approval_id,
        "requester": "dave",
        "reason": "No sig",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "granted",
        "approver": "eve",
        "signature_meta": None,
        "grant_timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    temp_state.write_text(json.dumps(record) + "\n")
    
    valid, message = verifier.verify_approval(approval_id)
    
    assert not valid
    assert "signature" in message.lower()


def test_verify_approval_invalid_signature(temp_state, monkeypatch):
    """Test verify_approval fails for invalid signature."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    approval_id = "test-uuid-3456"
    timestamp = datetime.now(timezone.utc).isoformat()
    
    record = {
        "approval_id": approval_id,
        "requester": "frank",
        "reason": "Bad sig",
        "timestamp": timestamp,
        "status": "granted",
        "approver": "grace",
        "signature_meta": {
            "method": "hmac-sha256",
            "signature": "invalid-signature-hash",
            "signed_hash": "fake-hash",
            "approver": "grace",
            "grant_timestamp": datetime.now(timezone.utc).isoformat()
        },
        "grant_timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    temp_state.write_text(json.dumps(record) + "\n")
    
    valid, message = verifier.verify_approval(approval_id)
    
    assert not valid
    assert "verification failed" in message.lower()


def test_verify_approval_expired(temp_state, monkeypatch):
    """Test verify_approval fails for expired approval."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    approval_id = "test-uuid-7890"
    
    # Create approval granted 100 hours ago
    old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
    request_timestamp = old_timestamp
    
    from supervision.signature_utils import canonical_payload, sign_payload
    
    payload = canonical_payload(approval_id, "heidi", "Old approval", request_timestamp, "granted")
    sig_meta = sign_payload(payload)
    sig_meta["approver"] = "ivan"
    sig_meta["grant_timestamp"] = old_timestamp
    
    record = {
        "approval_id": approval_id,
        "requester": "heidi",
        "reason": "Old approval",
        "timestamp": request_timestamp,
        "status": "granted",
        "approver": "ivan",
        "signature_meta": sig_meta,
        "grant_timestamp": old_timestamp
    }
    
    temp_state.write_text(json.dumps(record) + "\n")
    
    valid, message = verifier.verify_approval(approval_id, ttl_hours=72)
    
    assert not valid
    assert "expired" in message.lower()


def test_verify_approval_custom_ttl(temp_state, monkeypatch):
    """Test verify_approval respects custom TTL."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    approval_id = "test-uuid-1111"
    
    # Create approval granted 50 hours ago
    grant_timestamp = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    request_timestamp = grant_timestamp
    
    from supervision.signature_utils import canonical_payload, sign_payload
    
    payload = canonical_payload(approval_id, "judy", "Custom TTL", request_timestamp, "granted")
    sig_meta = sign_payload(payload)
    sig_meta["approver"] = "kevin"
    sig_meta["grant_timestamp"] = grant_timestamp
    
    record = {
        "approval_id": approval_id,
        "requester": "judy",
        "reason": "Custom TTL",
        "timestamp": request_timestamp,
        "status": "granted",
        "approver": "kevin",
        "signature_meta": sig_meta,
        "grant_timestamp": grant_timestamp
    }
    
    temp_state.write_text(json.dumps(record) + "\n")
    
    # Should pass with 72h TTL
    valid_72, _ = verifier.verify_approval(approval_id, ttl_hours=72)
    assert valid_72
    
    # Should fail with 24h TTL
    valid_24, message_24 = verifier.verify_approval(approval_id, ttl_hours=24)
    assert not valid_24
    assert "expired" in message_24.lower()


def test_verify_approval_skips_comments(temp_state, monkeypatch):
    """Test verify_approval ignores comment lines."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    approval_id = "test-uuid-2222"
    timestamp = datetime.now(timezone.utc).isoformat()
    grant_timestamp = datetime.now(timezone.utc).isoformat()
    
    from supervision.signature_utils import canonical_payload, sign_payload
    
    payload = canonical_payload(approval_id, "laura", "With comments", timestamp, "granted")
    sig_meta = sign_payload(payload)
    sig_meta["approver"] = "mike"
    sig_meta["grant_timestamp"] = grant_timestamp
    
    record = {
        "approval_id": approval_id,
        "requester": "laura",
        "reason": "With comments",
        "timestamp": timestamp,
        "status": "granted",
        "approver": "mike",
        "signature_meta": sig_meta,
        "grant_timestamp": grant_timestamp
    }
    
    content = "<!-- HUMAN_APPROVAL: GRANTED 2025-01-01T00:00:00+00:00 -->\n"
    content += json.dumps(record) + "\n"
    content += "<!-- Another comment -->\n"
    
    temp_state.write_text(content)
    
    valid, message = verifier.verify_approval(approval_id)
    
    assert valid
    assert "Valid" in message
