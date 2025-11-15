#!/usr/bin/env python3
"""
Verify approval signature and status.
Used by CI approval gate workflow.
Exit 0 if valid, 1 if invalid/expired/missing.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))
from signature_utils import canonical_payload, verify_signature


APPROVAL_REQUESTS = Path("state/approval_requests.jsonl")
DEFAULT_TTL_HOURS = 72


def verify_approval(approval_id: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> tuple[bool, str]:
    """Verify approval is granted, signed, and within TTL."""
    if not APPROVAL_REQUESTS.exists():
        return False, "No approval requests found"
    
    # Load requests (skip comments)
    lines = [ln for ln in APPROVAL_REQUESTS.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("<!--")]
    
    if not lines:
        return False, "No approval records"
    
    requests = [json.loads(ln) for ln in lines]
    req = next((r for r in requests if r["approval_id"] == approval_id), None)
    
    if not req:
        return False, f"Approval ID {approval_id} not found"
    
    if req["status"] != "granted":
        return False, f"Approval status is {req['status']}, not granted"
    
    if not req.get("signature_meta"):
        return False, "No signature metadata present"
    
    sig_meta = req["signature_meta"]
    
    # Verify signature
    payload = canonical_payload(
        approval_id,
        req["requester"],
        req["reason"],
        req["timestamp"],
        "granted"
    )
    
    if not verify_signature(payload, sig_meta["signature"], sig_meta["method"]):
        return False, "Signature verification failed"
    
    # Check TTL
    grant_ts = datetime.fromisoformat(req["grant_timestamp"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    age = now - grant_ts
    
    if age > timedelta(hours=ttl_hours):
        return False, f"Approval expired ({age.total_seconds() / 3600:.1f}h old, TTL {ttl_hours}h)"
    
    return True, "Valid approval"


def main():
    parser = argparse.ArgumentParser(description="Verify approval for CI gate")
    parser.add_argument("--id", required=True, help="Approval ID to verify")
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL_HOURS, help="TTL in hours (default 72)")
    
    args = parser.parse_args()
    
    valid, message = verify_approval(args.id, args.ttl)
    
    if valid:
        print(f"✓ {message}: {args.id}")
        sys.exit(0)
    else:
        print(f"✗ {message}", file=sys.stderr)
        
        # Append audit marker
        marker = f"<!-- APPROVAL_GATE: DENIED {datetime.now(timezone.utc).isoformat()} -->"
        if APPROVAL_REQUESTS.exists():
            content = APPROVAL_REQUESTS.read_text(encoding="utf-8")
            APPROVAL_REQUESTS.write_text(content + marker + "\n", encoding="utf-8")
        
        sys.exit(1)


if __name__ == "__main__":
    main()
