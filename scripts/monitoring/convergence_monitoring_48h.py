#!/usr/bin/env python3
"""
48-Hour Convergence Monitoring Setup
Verifies convergence_score stability post-release v2.18.0-mvcrs-stable-main
Executes every 4 hours for 48 hours starting 2025-11-15T10:15:00Z
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

def check_convergence_state():
    """Read and verify convergence state file."""
    state_file = Path("state/mvcrs_stability_convergence.json")
    
    if not state_file.exists():
        return {"error": "State file not found", "file": str(state_file)}
    
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        return state
    except Exception as e:
        return {"error": f"Failed to read state: {str(e)}"}

def evaluate_monitoring_status(state):
    """Evaluate convergence score against monitoring thresholds."""
    if "error" in state:
        return {
            "status": "ERROR",
            "message": state["error"],
            "action": "INVESTIGATE"
        }
    
    score = state.get("convergence_score", 0)
    alignment = state.get("alignment_status", "unknown")
    
    if score < 0.30:
        return {
            "status": "CRITICAL",
            "score": score,
            "alignment": alignment,
            "action": "ESCALATE_INCIDENT",
            "message": "convergence_score < 0.30 — critical threshold; consider auto-rollback"
        }
    elif score < 0.40:
        return {
            "status": "ALERT",
            "score": score,
            "alignment": alignment,
            "action": "CONTINUE_MONITORING",
            "message": f"convergence_score {score:.4f} < 0.40 — in alert zone; continue tracking"
        }
    elif score >= 0.45:
        return {
            "status": "RECOVERED",
            "score": score,
            "alignment": alignment,
            "action": "CLOSE_MONITORING",
            "message": f"convergence_score {score:.4f} >= 0.45 — merge validated; close monitoring"
        }
    else:
        return {
            "status": "CAUTION",
            "score": score,
            "alignment": alignment,
            "action": "CONTINUE_MONITORING",
            "message": f"convergence_score {score:.4f} in caution range; continue tracking"
        }

def log_monitoring_checkpoint(check_num, state, evaluation):
    """Log monitoring checkpoint to append-only file."""
    log_file = Path("logs/convergence_monitoring_48h.jsonl")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    checkpoint = {
        "check_number": check_num,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "convergence_score": state.get("convergence_score"),
        "alignment_status": state.get("alignment_status"),
        "ensemble_confidence": state.get("ensemble_confidence"),
        "monitoring_status": evaluation["status"],
        "action": evaluation["action"],
        "message": evaluation.get("message")
    }
    
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(checkpoint, separators=(',', ':')) + '\n')
        return True
    except Exception as e:
        print(f"ERROR: Failed to log checkpoint: {e}", file=sys.stderr)
        return False

def main():
    """Execute monitoring checkpoint."""
    print("[Monitoring] 48-Hour Convergence Stability Checkpoint")
    print(f"[Timestamp] {datetime.utcnow().isoformat()}Z")
    print()
    
    state = check_convergence_state()
    evaluation = evaluate_monitoring_status(state)
    
    # Determine checkpoint number (could be passed as argument)
    check_num = 1  # First check post-release
    
    # Log the checkpoint
    log_ok = log_monitoring_checkpoint(check_num, state, evaluation)
    
    # Display results
    print(f"[Status] {evaluation['status']}")
    print(f"[Score] {state.get('convergence_score', 'N/A')}")
    print(f"[Alignment] {state.get('alignment_status', 'N/A')}")
    print(f"[Action] {evaluation['action']}")
    print(f"[Message] {evaluation['message']}")
    print()
    
    if log_ok:
        print("[Log] Checkpoint recorded to logs/convergence_monitoring_48h.jsonl")
    else:
        print("[WARNING] Checkpoint logging failed")
    
    # Exit codes
    if evaluation["status"] == "CRITICAL":
        sys.exit(2)  # Incident escalation
    elif evaluation["status"] == "ERROR":
        sys.exit(1)  # Error
    else:
        sys.exit(0)  # Continue monitoring

if __name__ == "__main__":
    main()
