#!/usr/bin/env python3
"""Tests for signature utilities."""

import os
import sys
from pathlib import Path

import pytest

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from supervision.signature_utils import (
    canonical_payload,
    compute_hash,
    sign_payload,
    verify_signature
)


def test_canonical_payload():
    """Test canonical payload formatting."""
    payload = canonical_payload(
        "approval-id-123",
        "alice",
        "Test reason",
        "2025-01-01T00:00:00Z",
        "granted"
    )
    
    expected = "approval-id-123|alice|Test reason|2025-01-01T00:00:00Z|granted"
    assert payload == expected


def test_compute_hash_deterministic():
    """Test compute_hash produces deterministic SHA-256."""
    payload1 = "test payload"
    payload2 = "test payload"
    payload3 = "different payload"
    
    hash1 = compute_hash(payload1)
    hash2 = compute_hash(payload2)
    hash3 = compute_hash(payload3)
    
    assert hash1 == hash2
    assert hash1 != hash3
    assert len(hash1) == 64  # SHA-256 hex


def test_sign_payload_hmac(monkeypatch):
    """Test sign_payload with HMAC-SHA256."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    payload = "test payload for signing"
    result = sign_payload(payload)
    
    assert result["method"] == "hmac-sha256"
    assert "signature" in result
    assert "signed_hash" in result
    assert len(result["signature"]) == 64  # HMAC-SHA256 hex


def test_sign_payload_pgp_stub(monkeypatch):
    """Test sign_payload with PGP-like stub."""
    monkeypatch.setenv("SIGNING_KEY", "test-pgp-key")
    
    payload = "test payload for pgp"
    result = sign_payload(payload)
    
    assert result["method"] == "pgp"
    assert result["signature"].startswith("PGP:")
    assert "signed_hash" in result


def test_sign_payload_unsigned_fallback():
    """Test sign_payload falls back to unsigned when no key."""
    # Ensure no env vars set
    os.environ.pop("SIGNING_SECRET", None)
    os.environ.pop("SIGNING_KEY", None)
    
    payload = "test payload unsigned"
    result = sign_payload(payload)
    
    assert result["method"] == "unsigned"
    assert result["signature"] == result["signed_hash"]


def test_verify_signature_hmac_valid(monkeypatch):
    """Test verify_signature succeeds for valid HMAC."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    payload = "test verification payload"
    sig_result = sign_payload(payload)
    
    valid = verify_signature(payload, sig_result["signature"], sig_result["method"])
    
    assert valid


def test_verify_signature_hmac_invalid(monkeypatch):
    """Test verify_signature fails for invalid HMAC."""
    monkeypatch.setenv("SIGNING_SECRET", "test-secret")
    
    payload = "original payload"
    sig_result = sign_payload(payload)
    
    # Try to verify different payload with same signature
    different_payload = "tampered payload"
    valid = verify_signature(different_payload, sig_result["signature"], sig_result["method"])
    
    assert not valid


def test_verify_signature_hmac_wrong_secret(monkeypatch):
    """Test verify_signature fails with wrong secret."""
    monkeypatch.setenv("SIGNING_SECRET", "original-secret")
    
    payload = "test payload"
    sig_result = sign_payload(payload)
    
    # Change secret
    monkeypatch.setenv("SIGNING_SECRET", "different-secret")
    
    valid = verify_signature(payload, sig_result["signature"], sig_result["method"])
    
    assert not valid


def test_verify_signature_pgp_valid(monkeypatch):
    """Test verify_signature succeeds for valid PGP stub."""
    monkeypatch.setenv("SIGNING_KEY", "test-pgp-key")
    
    payload = "test pgp verification"
    sig_result = sign_payload(payload)
    
    valid = verify_signature(payload, sig_result["signature"], sig_result["method"])
    
    assert valid


def test_verify_signature_pgp_invalid(monkeypatch):
    """Test verify_signature fails for invalid PGP stub."""
    monkeypatch.setenv("SIGNING_KEY", "test-pgp-key")
    
    payload = "original payload"
    sig_result = sign_payload(payload)
    
    # Tamper with signature
    tampered_sig = "PGP:" + "0" * 64
    valid = verify_signature(payload, tampered_sig, "pgp")
    
    assert not valid


def test_verify_signature_unsigned_valid():
    """Test verify_signature succeeds for unsigned (hash match)."""
    os.environ.pop("SIGNING_SECRET", None)
    os.environ.pop("SIGNING_KEY", None)
    
    payload = "unsigned payload"
    sig_result = sign_payload(payload)
    
    valid = verify_signature(payload, sig_result["signature"], sig_result["method"])
    
    assert valid


def test_verify_signature_unsigned_invalid():
    """Test verify_signature fails for unsigned (hash mismatch)."""
    os.environ.pop("SIGNING_SECRET", None)
    os.environ.pop("SIGNING_KEY", None)
    
    payload = "original payload"
    sig_result = sign_payload(payload)
    
    different_payload = "tampered payload"
    valid = verify_signature(different_payload, sig_result["signature"], sig_result["method"])
    
    assert not valid


def test_verify_signature_unknown_method():
    """Test verify_signature fails for unknown method."""
    payload = "test payload"
    signature = "fake-signature"
    
    valid = verify_signature(payload, signature, "unknown-method")
    
    assert not valid


def test_verify_signature_no_key_for_method(monkeypatch):
    """Test verify_signature fails when key not available."""
    os.environ.pop("SIGNING_SECRET", None)
    os.environ.pop("SIGNING_KEY", None)
    
    payload = "test payload"
    
    # Try to verify HMAC without secret
    valid = verify_signature(payload, "fake-sig", "hmac-sha256")
    assert not valid
    
    # Try to verify PGP without key
    valid = verify_signature(payload, "PGP:fake", "pgp")
    assert not valid


def test_signature_chain_integrity():
    """Test signature chain maintains integrity across multiple operations."""
    os.environ["SIGNING_SECRET"] = "chain-test-secret"
    
    payloads = [
        "first payload",
        "second payload",
        "third payload"
    ]
    
    signatures = []
    
    for payload in payloads:
        sig_result = sign_payload(payload)
        signatures.append(sig_result)
        
        # Verify immediately
        valid = verify_signature(payload, sig_result["signature"], sig_result["method"])
        assert valid
    
    # Verify all signatures remain valid
    for payload, sig_result in zip(payloads, signatures):
        valid = verify_signature(payload, sig_result["signature"], sig_result["method"])
        assert valid
    
    # Cross-check: signature from payload 1 should not validate payload 2
    invalid = verify_signature(payloads[1], signatures[0]["signature"], signatures[0]["method"])
    assert not invalid
