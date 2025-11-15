#!/usr/bin/env python3
"""
Human-in-the-loop approval API.
Provides request/grant workflow with atomic writes, fix-branch on failure, idempotent audit markers.
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent to path for signature_utils import
sys.path.insert(0, str(Path(__file__).parent))
from signature_utils import canonical_payload, sign_payload


STATE_DIR = Path("state")
APPROVAL_STATE = STATE_DIR / "approval_state.json"
APPROVAL_REQUESTS = STATE_DIR / "approval_requests.jsonl"
APPROVAL_HIGHWATER = STATE_DIR / "approval_highwater.json"


def atomic_write_json(path: Path, data: Any, retries: int = 3) -> None:
    """Atomic write with 1s/3s/9s retry."""
    delays = [1, 3, 9]
    tmp = path.with_suffix(".tmp")
    
    for attempt in range(retries):
        try:
            tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            tmp.replace(path)
            return
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delays[attempt])
            else:
                create_fix_branch(path, e)
                raise


def append_to_jsonl(path: Path, record: Dict) -> None:
    """Append JSON record to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def create_fix_branch(path: Path, error: Exception) -> None:
    """Create fix branch with diagnostics."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fix_dir = Path(f"fix/trust-approval-{ts}")
    fix_dir.mkdir(parents=True, exist_ok=True)
    
    diag = {
        "error": str(error),
        "file": str(path),
        "timestamp": ts,
        "cwd": os.getcwd()
    }
    (fix_dir / "diag.json").write_text(json.dumps(diag, indent=2))
    print(f"Fix branch created: {fix_dir}", file=sys.stderr)


def append_audit_marker(marker: str) -> None:
    """Idempotently append audit marker to approval requests."""
    if not APPROVAL_REQUESTS.exists():
        return
    
    content = APPROVAL_REQUESTS.read_text(encoding="utf-8")
    prefix = "<!-- HUMAN_APPROVAL:"
    
    # Remove existing marker
    lines = [ln for ln in content.splitlines() if not ln.startswith(prefix)]
    
    # Append new marker
    lines.append(marker)
    
    APPROVAL_REQUESTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_status() -> Dict[str, Any]:
    """GET /approval/status - return current approval state."""
    if APPROVAL_STATE.exists():
        return json.loads(APPROVAL_STATE.read_text(encoding="utf-8"))
    else:
        return {
            "status": "unlocked",
            "approval_id": None,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }


def request_approval(requester: str, reason: str) -> Dict[str, str]:
    """POST /approval/request - create new approval request."""
    approval_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    
    record = {
        "approval_id": approval_id,
        "requester": requester,
        "reason": reason,
        "timestamp": timestamp,
        "status": "requested",
        "approver": None,
        "signature_meta": None
    }
    
    append_to_jsonl(APPROVAL_REQUESTS, record)
    
    # Update state
    state = {
        "status": "pending_approval",
        "approval_id": approval_id,
        "last_updated": timestamp
    }
    atomic_write_json(APPROVAL_STATE, state)
    
    marker = f"<!-- HUMAN_APPROVAL: REQUESTED {timestamp} -->"
    append_audit_marker(marker)
    
    return {
        "approval_id": approval_id,
        "status": "requested",
        "message": f"Approval request created: {approval_id}"
    }


def grant_approval(approval_id: str, approver: str) -> Dict[str, Any]:
    """POST /approval/grant - grant approval with signature."""
    # Load requests
    if not APPROVAL_REQUESTS.exists():
        return {"error": "No approval requests found", "status": "error"}
    
    lines = [ln for ln in APPROVAL_REQUESTS.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("<!--")]
    requests = [json.loads(ln) for ln in lines]
    
    # Find matching request
    req = next((r for r in requests if r["approval_id"] == approval_id), None)
    if not req:
        return {"error": f"Approval ID {approval_id} not found", "status": "error"}
    
    if req["status"] == "granted":
        return {"error": "Approval already granted", "status": "error"}
    
    # Check daily limit
    if not check_daily_limit(approver):
        marker = f"<!-- APPROVAL_LIMIT: EXCEEDED {datetime.now(timezone.utc).isoformat()} -->"
        append_audit_marker(marker)
        return {"error": "Daily approval limit exceeded", "status": "error", "http_code": 403}
    
    # Sign
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = canonical_payload(approval_id, req["requester"], req["reason"], req["timestamp"], "granted")
    sig_meta = sign_payload(payload)
    sig_meta["approver"] = approver
    sig_meta["grant_timestamp"] = timestamp
    
    # Update request
    req["status"] = "granted"
    req["approver"] = approver
    req["signature_meta"] = sig_meta
    req["grant_timestamp"] = timestamp
    
    # Rewrite JSONL
    updated_lines = [json.dumps(r) for r in requests]
    APPROVAL_REQUESTS.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    
    # Update state
    state = {
        "status": "approved",
        "approval_id": approval_id,
        "approver": approver,
        "last_updated": timestamp
    }
    atomic_write_json(APPROVAL_STATE, state)
    
    # Increment highwater
    increment_highwater(approver)
    
    marker = f"<!-- HUMAN_APPROVAL: GRANTED {timestamp} -->"
    append_audit_marker(marker)
    
    return {
        "approval_id": approval_id,
        "status": "granted",
        "approver": approver,
        "signature": sig_meta["signature"],
        "message": "Approval granted successfully"
    }


def check_daily_limit(approver: str, limit: int = 5) -> bool:
    """Check if approver has exceeded daily grant limit."""
    today = datetime.now(timezone.utc).date().isoformat()
    
    if APPROVAL_HIGHWATER.exists():
        hw = json.loads(APPROVAL_HIGHWATER.read_text(encoding="utf-8"))
    else:
        hw = {}
    
    key = f"{approver}:{today}"
    return hw.get(key, 0) < limit


def increment_highwater(approver: str) -> None:
    """Increment daily highwater count for approver."""
    today = datetime.now(timezone.utc).date().isoformat()
    
    if APPROVAL_HIGHWATER.exists():
        hw = json.loads(APPROVAL_HIGHWATER.read_text(encoding="utf-8"))
    else:
        hw = {}
    
    key = f"{approver}:{today}"
    hw[key] = hw.get(key, 0) + 1
    
    atomic_write_json(APPROVAL_HIGHWATER, hw)


def override_approval(override_key: str, approval_id: str, requester: str, reason: str) -> Dict[str, Any]:
    """Emergency override requiring OVERRIDE_KEY."""
    expected_key = os.getenv("OVERRIDE_KEY")
    if not expected_key or override_key != expected_key:
        return {"error": "Invalid override key", "status": "error", "http_code": 403}
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    record = {
        "approval_id": approval_id,
        "requester": requester,
        "reason": reason,
        "timestamp": timestamp,
        "status": "granted",
        "approver": "OVERRIDE",
        "signature_meta": {
            "method": "override",
            "signature": "EMERGENCY_OVERRIDE",
            "signed_hash": "N/A",
            "approver": "OVERRIDE",
            "grant_timestamp": timestamp
        },
        "grant_timestamp": timestamp
    }
    
    append_to_jsonl(APPROVAL_REQUESTS, record)
    
    state = {
        "status": "approved",
        "approval_id": approval_id,
        "approver": "OVERRIDE",
        "last_updated": timestamp
    }
    atomic_write_json(APPROVAL_STATE, state)
    
    marker = f"<!-- APPROVAL_OVERRIDE: USED {timestamp} -->"
    append_audit_marker(marker)
    
    return {
        "approval_id": approval_id,
        "status": "granted",
        "approver": "OVERRIDE",
        "message": "Emergency override applied"
    }


if __name__ == "__main__":
    print("Human Approval API - use via CLI or import as module")
