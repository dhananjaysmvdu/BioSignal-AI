#!/usr/bin/env python3
"""
MV-CRS Escalation Lifecycle Engine

Manages the deterministic state machine for escalation lifecycle:
- pending → in_progress → corrective_action_applied → awaiting_validation → resolved/rejected

Auto-transition rules:
- Verifier failed → create escalation (pending)
- Pending >24h → in_progress
- Correction artifact present → awaiting_validation
- Validation success → resolved
- Validation fail → rejected

Emits:
- state/mvcrs_escalation_lifecycle.json
- state/mvcrs_escalation_lifecycle_log.jsonl
- Updates docs/audit_summary.md with idempotent marker

Safety:
- Atomic writes with 1s/3s/9s retry
- Fix-branch creation on persistent FS error
- MVCRS_BASE_DIR support for tests
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from challenge_utils import atomic_write_json, append_jsonl


# ============================================================================
# Path Utilities (MVCRS_BASE_DIR virtualization)
# ============================================================================

def _p(rel: str) -> Path:
    """Resolve path relative to MVCRS_BASE_DIR or project root."""
    base = os.getenv("MVCRS_BASE_DIR")
    if base:
        return Path(base) / rel
    return Path(__file__).parent.parent.parent / rel


# ============================================================================
# Escalation Lifecycle States
# ============================================================================

LIFECYCLE_STATES = [
    "pending",
    "in_progress",
    "corrective_action_applied",
    "awaiting_validation",
    "resolved",
    "rejected"
]

# Terminal states (no further transitions)
TERMINAL_STATES = {"resolved", "rejected"}


# ============================================================================
# Load Input Artifacts
# ============================================================================

def load_verifier_state() -> Optional[Dict[str, Any]]:
    """Load challenge_verifier_state.json if present."""
    path = _p("state/challenge_verifier_state.json")
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load verifier state: {e}", file=sys.stderr)
        return None


def load_correction_state() -> Optional[Dict[str, Any]]:
    """Load mvcrs_last_correction.json if present."""
    path = _p("state/mvcrs_last_correction.json")
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load correction state: {e}", file=sys.stderr)
        return None


def load_escalation() -> Optional[Dict[str, Any]]:
    """Load mvcrs_escalation.json if present."""
    path = _p("state/mvcrs_escalation.json")
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load escalation: {e}", file=sys.stderr)
        return None


def load_lifecycle_state() -> Optional[Dict[str, Any]]:
    """Load existing mvcrs_escalation_lifecycle.json if present."""
    path = _p("state/mvcrs_escalation_lifecycle.json")
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load lifecycle state: {e}", file=sys.stderr)
        return None


# ============================================================================
# State Machine Transition Logic
# ============================================================================

def should_create_escalation(verifier_state: Optional[Dict], escalation: Optional[Dict]) -> bool:
    """Determine if a new escalation should be created."""
    if escalation is not None:
        return False  # Already exists
    if verifier_state is None:
        return False
    return verifier_state.get("status") == "failed"


def should_transition_to_in_progress(lifecycle: Dict) -> bool:
    """Pending >24h → in_progress."""
    if lifecycle.get("current_state") != "pending":
        return False
    entered_at_str = lifecycle.get("entered_current_state_at")
    if not entered_at_str:
        return False
    try:
        entered_at = datetime.fromisoformat(entered_at_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        elapsed = now - entered_at
        return elapsed > timedelta(hours=24)
    except Exception:
        return False


def should_transition_to_awaiting_validation(lifecycle: Dict, correction_state: Optional[Dict]) -> bool:
    """Correction artifact present → awaiting_validation."""
    if lifecycle.get("current_state") not in {"in_progress", "corrective_action_applied"}:
        return False
    if correction_state is None:
        return False
    # Check if correction was applied
    correction_type = correction_state.get("correction_type")
    return correction_type in {"soft", "hard"}


def should_transition_to_resolved(lifecycle: Dict, verifier_state: Optional[Dict]) -> bool:
    """Validation success (verifier status ok) → resolved."""
    if lifecycle.get("current_state") != "awaiting_validation":
        return False
    if verifier_state is None:
        return False
    return verifier_state.get("status") == "ok"


def should_transition_to_rejected(lifecycle: Dict, verifier_state: Optional[Dict]) -> bool:
    """Validation fail (verifier still failed after correction) → rejected."""
    if lifecycle.get("current_state") != "awaiting_validation":
        return False
    if verifier_state is None:
        return False
    # Check if verifier ran after correction was applied
    return verifier_state.get("status") in {"failed", "warning"}


def compute_next_state(
    lifecycle: Optional[Dict],
    verifier_state: Optional[Dict],
    correction_state: Optional[Dict],
    escalation: Optional[Dict]
) -> tuple[str, str]:
    """
    Compute next state and transition reason.
    Returns: (next_state, reason)
    """
    # Create new escalation if needed
    if should_create_escalation(verifier_state, escalation):
        return "pending", "Verifier failed - escalation created"

    # If no lifecycle state exists yet, initialize
    if lifecycle is None:
        if escalation is not None:
            return "pending", "Initial lifecycle state for existing escalation"
        return "pending", "No escalation present"

    current_state = lifecycle.get("current_state", "pending")

    # Terminal states
    if current_state in TERMINAL_STATES:
        return current_state, f"Terminal state: {current_state}"

    # Pending → in_progress (24h threshold)
    if should_transition_to_in_progress(lifecycle):
        return "in_progress", "Pending >24h - escalating to in_progress"

    # In_progress/corrective_action_applied → awaiting_validation
    if should_transition_to_awaiting_validation(lifecycle, correction_state):
        return "awaiting_validation", "Correction artifact detected"

    # Awaiting_validation → resolved
    if should_transition_to_resolved(lifecycle, verifier_state):
        return "resolved", "Validation passed - verifier status ok"

    # Awaiting_validation → rejected
    if should_transition_to_rejected(lifecycle, verifier_state):
        return "rejected", "Validation failed - verifier still failing"

    # No transition
    return current_state, "No transition criteria met"


# ============================================================================
# Lifecycle State Management
# ============================================================================

def build_lifecycle_state(
    current_state: str,
    reason: str,
    verifier_state: Optional[Dict],
    correction_state: Optional[Dict],
    escalation: Optional[Dict],
    previous_lifecycle: Optional[Dict]
) -> Dict[str, Any]:
    """Build the lifecycle state JSON."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Track counters
    resolved_count = previous_lifecycle.get("resolved_count", 0) if previous_lifecycle else 0
    rejected_count = previous_lifecycle.get("rejected_count", 0) if previous_lifecycle else 0
    
    # Increment counters on terminal transitions
    previous_state = previous_lifecycle.get("current_state") if previous_lifecycle else None
    if current_state == "resolved" and previous_state != "resolved":
        resolved_count += 1
    if current_state == "rejected" and previous_state != "rejected":
        rejected_count += 1
    
    # Time in current state
    entered_at = now
    if previous_lifecycle and previous_lifecycle.get("current_state") == current_state:
        # State unchanged - preserve entry time
        entered_at = previous_lifecycle.get("entered_current_state_at", now)
    
    state = {
        "timestamp": now,
        "current_state": current_state,
        "entered_current_state_at": entered_at,
        "last_transition_reason": reason,
        "resolved_count": resolved_count,
        "rejected_count": rejected_count,
        "verifier_status": verifier_state.get("status") if verifier_state else None,
        "correction_applied": correction_state is not None,
        "escalation_present": escalation is not None,
    }
    
    return state


# ============================================================================
# Output Writers
# ============================================================================

def write_lifecycle_state(state: Dict[str, Any]) -> bool:
    """Write lifecycle state with atomic writes and retries."""
    path = _p("state/mvcrs_escalation_lifecycle.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    delays = [1, 3, 9]
    for attempt, delay in enumerate(delays, 1):
        try:
            atomic_write_json(path, state)
            return True
        except Exception as e:
            if attempt == len(delays):
                print(f"Error: Failed to write lifecycle state after {attempt} attempts: {e}", file=sys.stderr)
                return False
            time.sleep(delay)
    return False


def append_lifecycle_log(entry: Dict[str, Any]) -> bool:
    """Append to lifecycle log JSONL."""
    path = _p("state/mvcrs_escalation_lifecycle_log.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    delays = [1, 3, 9]
    for attempt, delay in enumerate(delays, 1):
        try:
            append_jsonl(path, entry)
            return True
        except Exception as e:
            if attempt == len(delays):
                print(f"Error: Failed to append lifecycle log after {attempt} attempts: {e}", file=sys.stderr)
                return False
            time.sleep(delay)
    return False


def update_audit_marker() -> bool:
    """Update audit_summary.md with idempotent MVCRS_ESCALATION_LIFECYCLE marker."""
    audit_path = _p("docs/audit_summary.md")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Ensure file exists
    if not audit_path.exists():
        audit_path.write_text("# Audit Summary\n\n", encoding="utf-8")
    
    marker_prefix = "<!-- MVCRS_ESCALATION_LIFECYCLE:"
    now = datetime.now(timezone.utc).isoformat()
    new_marker = f"{marker_prefix} UPDATED {now} -->\n"
    
    try:
        content = audit_path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        
        # Remove existing marker
        lines = [line for line in lines if not line.strip().startswith(marker_prefix)]
        
        # Append new marker
        if not content.endswith("\n"):
            lines.append("\n")
        lines.append(new_marker)
        
        audit_path.write_text("".join(lines), encoding="utf-8")
        return True
    except Exception as e:
        print(f"Error: Failed to update audit marker: {e}", file=sys.stderr)
        return False


# ============================================================================
# Fix Branch Creation
# ============================================================================

def create_fix_branch() -> bool:
    """Create fix branch on persistent FS failure."""
    if os.getenv("MVCRS_BASE_DIR"):
        # Test mode - skip git operations
        return True
    
    try:
        import subprocess
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        branch_name = f"fix/mvcrs-escalation-lifecycle-{ts}"
        
        subprocess.run(["git", "checkout", "-b", branch_name], check=True, capture_output=True)
        
        # Commit diagnostic state
        subprocess.run(["git", "add", "state/", "docs/audit_summary.md"], check=False, capture_output=True)
        subprocess.run([
            "git", "commit", "-m",
            f"chore(mvcrs): escalation lifecycle FS failure diagnostics [{ts}]"
        ], check=False, capture_output=True)
        
        print(f"Created fix branch: {branch_name}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"Warning: Failed to create fix branch: {e}", file=sys.stderr)
        return False


# ============================================================================
# Main Orchestration
# ============================================================================

def run_lifecycle_engine() -> int:
    """
    Main lifecycle engine execution.
    Returns: 0 on success, 1 on recoverable error, 2 on critical failure.
    """
    print("=== MV-CRS Escalation Lifecycle Engine ===")
    
    # Load inputs
    verifier_state = load_verifier_state()
    correction_state = load_correction_state()
    escalation = load_escalation()
    previous_lifecycle = load_lifecycle_state()
    
    print(f"Loaded: verifier={verifier_state is not None}, "
          f"correction={correction_state is not None}, "
          f"escalation={escalation is not None}, "
          f"lifecycle={previous_lifecycle is not None}")
    
    # Compute next state
    next_state, reason = compute_next_state(
        previous_lifecycle, verifier_state, correction_state, escalation
    )
    
    print(f"Transition: {previous_lifecycle.get('current_state') if previous_lifecycle else 'None'} "
          f"→ {next_state} (reason: {reason})")
    
    # Build new lifecycle state
    lifecycle_state = build_lifecycle_state(
        next_state, reason, verifier_state, correction_state, escalation, previous_lifecycle
    )
    
    # Write outputs
    success = True
    if not write_lifecycle_state(lifecycle_state):
        success = False
    
    log_entry = {
        **lifecycle_state,
        "transition_reason": reason
    }
    if not append_lifecycle_log(log_entry):
        success = False
    
    if not update_audit_marker():
        success = False
    
    if not success:
        print("Error: Failed to write outputs - attempting fix branch creation", file=sys.stderr)
        create_fix_branch()
        return 2
    
    print(f"✓ Lifecycle engine completed successfully")
    print(f"  State: {next_state}")
    print(f"  Resolved: {lifecycle_state['resolved_count']}, Rejected: {lifecycle_state['rejected_count']}")
    
    return 0


def main() -> int:
    """CLI entry point."""
    try:
        return run_lifecycle_engine()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
