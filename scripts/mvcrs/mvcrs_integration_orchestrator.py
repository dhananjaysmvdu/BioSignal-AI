#!/usr/bin/env python3
"""
MV-CRS Integration Orchestrator

Synthesizes all MV-CRS phases and upstream governance states into a unified
integration status with final decision framework.

Inputs:
- MV-CRS states: verifier, correction, escalation, lifecycle
- Governance states: policy fusion, thresholds, RDGL, trust lock

Outputs:
- state/mvcrs_integration_state.json (synthesized decision)
- logs/mvcrs_integration_log.jsonl (audit trail)
- docs/audit_summary.md (idempotent marker)

Decision Logic:
- allow: All systems healthy, no escalations, governance green
- restricted: Escalation open OR governance yellow OR lifecycle in progress
- blocked: Governance red + mvcrs_core_ok=false OR critical failures

Safety:
- Atomic writes with 1s/3s/9s retry
- Fix-branch creation on persistent failure
- MVCRS_BASE_DIR support for tests
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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
# Load MV-CRS States
# ============================================================================

def load_json_optional(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON file if it exists, return None otherwise."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load {path}: {e}", file=sys.stderr)
        return None


def load_mvcrs_states() -> Dict[str, Optional[Dict]]:
    """Load all MV-CRS phase outputs."""
    return {
        "verifier": load_json_optional(_p("state/challenge_verifier_state.json")),
        "correction": load_json_optional(_p("state/mvcrs_last_correction.json")),
        "escalation": load_json_optional(_p("state/mvcrs_escalation.json")),
        "lifecycle": load_json_optional(_p("state/mvcrs_escalation_lifecycle.json")),
    }


def load_governance_states() -> Dict[str, Optional[Dict]]:
    """Load upstream governance states."""
    return {
        "policy_fusion": load_json_optional(_p("state/policy_fusion_state.json")),
        "thresholds": load_json_optional(_p("state/threshold_policy.json")),
        "rdgl": load_json_optional(_p("state/rdgl_policy_adjustments.json")),
        "trust_lock": load_json_optional(_p("state/trust_lock_state.json")),
    }


# ============================================================================
# Status Analysis
# ============================================================================

def analyze_mvcrs_core_ok(mvcrs: Dict[str, Optional[Dict]]) -> bool:
    """Determine if MV-CRS core is healthy."""
    verifier = mvcrs.get("verifier")
    if verifier is None:
        return False  # No verifier state = not ok
    
    status = verifier.get("status", "unknown")
    if status == "failed":
        return False
    
    # Check if correction was blocked
    correction = mvcrs.get("correction")
    if correction:
        if correction.get("blocked_by_trust_lock") or correction.get("blocked_by_safety_brake"):
            return False
    
    return True


def analyze_escalation_open(mvcrs: Dict[str, Optional[Dict]]) -> bool:
    """Determine if escalation is currently open."""
    lifecycle = mvcrs.get("lifecycle")
    if lifecycle is None:
        return False
    
    current_state = lifecycle.get("current_state", "")
    # Terminal states mean escalation is closed
    return current_state not in {"resolved", "rejected", ""}


def get_lifecycle_state(mvcrs: Dict[str, Optional[Dict]]) -> str:
    """Get current lifecycle state."""
    lifecycle = mvcrs.get("lifecycle")
    if lifecycle is None:
        return "unknown"
    return lifecycle.get("current_state", "unknown")


def analyze_governance_risk_level(gov: Dict[str, Optional[Dict]]) -> str:
    """Derive governance risk level from upstream states."""
    policy_fusion = gov.get("policy_fusion")
    trust_lock = gov.get("trust_lock")
    
    # Check policy fusion state
    if policy_fusion:
        fusion_state = policy_fusion.get("fusion_state", "FUSION_GREEN")
        if fusion_state == "FUSION_RED":
            return "red"
        elif fusion_state == "FUSION_YELLOW":
            return "yellow"
    
    # Check trust lock
    if trust_lock:
        if trust_lock.get("locked", False):
            return "red"
    
    # Check RDGL mode
    rdgl = gov.get("rdgl")
    if rdgl:
        mode = rdgl.get("mode", "normal")
        if mode == "locked":
            return "red"
        elif mode == "tightening":
            return "yellow"
    
    return "green"


def compute_final_decision(
    mvcrs_core_ok: bool,
    escalation_open: bool,
    lifecycle_state: str,
    governance_risk: str
) -> str:
    """
    Compute final decision based on all signals.
    
    Decision Logic:
    - blocked: Governance red + mvcrs_core_ok=false OR critical failures
    - restricted: Escalation open OR governance yellow OR lifecycle in progress
    - allow: All systems healthy, no escalations, governance green
    """
    # Critical failure: governance red + MV-CRS not ok
    if governance_risk == "red" and not mvcrs_core_ok:
        return "blocked"
    
    # Critical lifecycle states
    if lifecycle_state in {"rejected"}:
        return "blocked"
    
    # Escalation open or governance yellow
    if escalation_open:
        return "restricted"
    
    if governance_risk == "yellow":
        return "restricted"
    
    # In-progress lifecycle states
    if lifecycle_state in {"pending", "in_progress", "awaiting_validation"}:
        return "restricted"
    
    # All clear
    if mvcrs_core_ok and governance_risk == "green":
        return "allow"
    
    # Default to restricted if ambiguous
    return "restricted"


# ============================================================================
# Build Integration State
# ============================================================================

def build_integration_state(
    mvcrs: Dict[str, Optional[Dict]],
    gov: Dict[str, Optional[Dict]]
) -> Dict[str, Any]:
    """Build synthesized integration state."""
    now = datetime.now(timezone.utc).isoformat()
    
    mvcrs_core_ok = analyze_mvcrs_core_ok(mvcrs)
    escalation_open = analyze_escalation_open(mvcrs)
    lifecycle_state = get_lifecycle_state(mvcrs)
    governance_risk = analyze_governance_risk_level(gov)
    final_decision = compute_final_decision(
        mvcrs_core_ok, escalation_open, lifecycle_state, governance_risk
    )
    
    return {
        "timestamp": now,
        "mvcrs_core_ok": mvcrs_core_ok,
        "escalation_open": escalation_open,
        "lifecycle_state": lifecycle_state,
        "governance_risk_level": governance_risk,
        "final_decision": final_decision,
        "inputs": {
            "verifier_status": mvcrs["verifier"].get("status") if mvcrs["verifier"] else None,
            "correction_type": mvcrs["correction"].get("correction_type") if mvcrs["correction"] else None,
            "lifecycle_resolved_count": mvcrs["lifecycle"].get("resolved_count", 0) if mvcrs["lifecycle"] else 0,
            "lifecycle_rejected_count": mvcrs["lifecycle"].get("rejected_count", 0) if mvcrs["lifecycle"] else 0,
            "policy_fusion_state": gov["policy_fusion"].get("fusion_state") if gov["policy_fusion"] else None,
            "trust_locked": gov["trust_lock"].get("locked") if gov["trust_lock"] else False,
            "rdgl_mode": gov["rdgl"].get("mode") if gov["rdgl"] else None,
        }
    }


# ============================================================================
# Output Writers
# ============================================================================

def write_integration_state(state: Dict[str, Any]) -> bool:
    """Write integration state with atomic writes and retries."""
    path = _p("state/mvcrs_integration_state.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    delays = [1, 3, 9]
    for attempt, delay in enumerate(delays, 1):
        try:
            atomic_write_json(path, state)
            return True
        except Exception as e:
            if attempt == len(delays):
                print(f"Error: Failed to write integration state after {attempt} attempts: {e}", file=sys.stderr)
                return False
            time.sleep(delay)
    return False


def append_integration_log(entry: Dict[str, Any]) -> bool:
    """Append to integration log JSONL."""
    path = _p("logs/mvcrs_integration_log.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    delays = [1, 3, 9]
    for attempt, delay in enumerate(delays, 1):
        try:
            append_jsonl(path, entry)
            return True
        except Exception as e:
            if attempt == len(delays):
                print(f"Error: Failed to append integration log after {attempt} attempts: {e}", file=sys.stderr)
                return False
            time.sleep(delay)
    return False


def update_audit_marker(status: str) -> bool:
    """
    Update audit_summary.md with idempotent MVCRS_INTEGRATION marker.
    
    Args:
        status: "UPDATED" or "FAILED"
    """
    audit_path = _p("docs/audit_summary.md")
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Ensure file exists
    if not audit_path.exists():
        audit_path.write_text("# Audit Summary\n\n", encoding="utf-8")
    
    marker_prefix = "<!-- MVCRS_INTEGRATION:"
    now = datetime.now(timezone.utc).isoformat()
    new_marker = f"{marker_prefix} {status} {now} -->\n"
    
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
        branch_name = f"fix/mvcrs-integration-{ts}"
        
        subprocess.run(["git", "checkout", "-b", branch_name], check=True, capture_output=True)
        
        # Commit diagnostic state
        subprocess.run([
            "git", "add",
            "state/mvcrs_integration_state.json",
            "logs/mvcrs_integration_log.jsonl",
            "docs/audit_summary.md"
        ], check=False, capture_output=True)
        
        subprocess.run([
            "git", "commit", "-m",
            f"chore(mvcrs): integration orchestrator FS failure diagnostics [{ts}]"
        ], check=False, capture_output=True)
        
        print(f"Created fix branch: {branch_name}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"Warning: Failed to create fix branch: {e}", file=sys.stderr)
        return False


# ============================================================================
# Main Orchestration
# ============================================================================

def run_integration_orchestrator() -> int:
    """
    Main integration orchestrator execution.
    Returns: 0 on success, 1 on recoverable error, 2 on critical failure.
    """
    print("=== MV-CRS Integration Orchestrator ===")
    
    # Load all inputs
    mvcrs_states = load_mvcrs_states()
    gov_states = load_governance_states()
    
    print(f"Loaded MV-CRS states: {sum(1 for v in mvcrs_states.values() if v is not None)}/4")
    print(f"Loaded governance states: {sum(1 for v in gov_states.values() if v is not None)}/4")
    
    # Build integration state
    integration_state = build_integration_state(mvcrs_states, gov_states)
    
    print(f"Integration Analysis:")
    print(f"  MV-CRS Core OK: {integration_state['mvcrs_core_ok']}")
    print(f"  Escalation Open: {integration_state['escalation_open']}")
    print(f"  Lifecycle State: {integration_state['lifecycle_state']}")
    print(f"  Governance Risk: {integration_state['governance_risk_level']}")
    print(f"  Final Decision: {integration_state['final_decision']}")
    
    # Write outputs
    success = True
    if not write_integration_state(integration_state):
        success = False
    
    log_entry = {**integration_state}
    if not append_integration_log(log_entry):
        success = False
    
    if not update_audit_marker("UPDATED" if success else "FAILED"):
        success = False
    
    if not success:
        print("Error: Failed to write outputs - attempting fix branch creation", file=sys.stderr)
        create_fix_branch()
        return 2
    
    print(f"✓ Integration orchestrator completed successfully")
    
    return 0


def main() -> int:
    """CLI entry point."""
    try:
        return run_integration_orchestrator()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
