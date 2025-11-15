#!/usr/bin/env python3
"""
Verify signature chain integrity for approval requests.
Ensures no tampering by checking signature hashes and prev_hash links.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))
from signature_utils import canonical_payload, verify_signature, compute_hash


APPROVAL_REQUESTS = Path("state/approval_requests.jsonl")


def verify_signatures_chain() -> tuple[bool, list[str]]:
    """
    Verify signature chain integrity.
    Returns (valid, messages).
    """
    if not APPROVAL_REQUESTS.exists():
        return True, ["No approval requests to verify"]
    
    content = APPROVAL_REQUESTS.read_text(encoding="utf-8")
    lines = [ln for ln in content.splitlines() if ln.strip() and not ln.startswith("<!--")]
    
    if not lines:
        return True, ["No approval records"]
    
    requests = [json.loads(ln) for ln in lines]
    messages = []
    prev_hash = None
    
    for idx, req in enumerate(requests):
        approval_id = req["approval_id"]
        status = req["status"]
        
        # Check signature if granted
        if status == "granted":
            sig_meta = req.get("signature_meta")
            
            if not sig_meta:
                messages.append(f"✗ {approval_id}: Missing signature metadata")
                return False, messages
            
            # Reconstruct payload
            payload = canonical_payload(
                approval_id,
                req["requester"],
                req["reason"],
                req["timestamp"],
                "granted"
            )
            
            # Verify signature
            if not verify_signature(payload, sig_meta["signature"], sig_meta["method"]):
                messages.append(f"✗ {approval_id}: Signature verification failed")
                return False, messages
            
            messages.append(f"✓ {approval_id}: Signature valid ({sig_meta['method']})")
        
        # Check prev_hash link (if present)
        if "prev_hash" in req:
            if prev_hash is None:
                messages.append(f"✗ {approval_id}: Has prev_hash but no previous record")
                return False, messages
            
            if req["prev_hash"] != prev_hash:
                messages.append(f"✗ {approval_id}: prev_hash mismatch (expected {prev_hash}, got {req['prev_hash']})")
                return False, messages
            
            messages.append(f"✓ {approval_id}: Chain link valid")
        
        # Compute hash for this record (for next link)
        record_str = json.dumps(req, sort_keys=True)
        prev_hash = compute_hash(record_str)
    
    messages.append(f"\n✓ Verified {len(requests)} approval records")
    return True, messages


def main():
    parser = argparse.ArgumentParser(description="Verify approval signature chain")
    args = parser.parse_args()
    
    valid, messages = verify_signatures_chain()
    
    for msg in messages:
        print(msg)
    
    if valid:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
