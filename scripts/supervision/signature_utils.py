#!/usr/bin/env python3
"""
Signature utilities for human approval tamper-evidence.
Supports HMAC-SHA256 or PGP-like signing via environment variables.
"""

import hashlib
import hmac
import os
from typing import Dict, Optional


def canonical_payload(
    approval_id: str,
    requester: str,
    reason: str,
    timestamp: str,
    status: str
) -> str:
    """Create canonical string for signing."""
    return f"{approval_id}|{requester}|{reason}|{timestamp}|{status}"


def compute_hash(payload: str) -> str:
    """Compute SHA-256 hash of payload."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sign_payload(payload: str) -> Dict[str, str]:
    """
    Sign payload using SIGNING_SECRET (HMAC) or SIGNING_KEY (PGP-like stub).
    Returns dict with method, signature, and signed_hash.
    """
    signing_secret = os.getenv("SIGNING_SECRET")
    signing_key = os.getenv("SIGNING_KEY")
    
    payload_hash = compute_hash(payload)
    
    if signing_key:
        # PGP-like stub: in production, use actual GPG/PGP signing
        signature = f"PGP:{compute_hash(signing_key + payload_hash)}"
        method = "pgp"
    elif signing_secret:
        signature = hmac.new(
            signing_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        method = "hmac-sha256"
    else:
        # Fallback: unsigned hash (weak, for dev only)
        signature = payload_hash
        method = "unsigned"
    
    return {
        "method": method,
        "signature": signature,
        "signed_hash": payload_hash
    }


def verify_signature(
    payload: str,
    signature: str,
    method: str
) -> bool:
    """Verify signature matches payload."""
    signing_secret = os.getenv("SIGNING_SECRET")
    signing_key = os.getenv("SIGNING_KEY")
    
    payload_hash = compute_hash(payload)
    
    if method == "pgp":
        if not signing_key:
            return False
        expected_sig = f"PGP:{compute_hash(signing_key + payload_hash)}"
        return signature == expected_sig
    elif method == "hmac-sha256":
        if not signing_secret:
            return False
        expected_sig = hmac.new(
            signing_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature == expected_sig
    elif method == "unsigned":
        return signature == payload_hash
    else:
        return False
