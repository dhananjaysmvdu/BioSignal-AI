#!/usr/bin/env python3
"""
Policy Fusion Engine - System-Wide Policy Integration

Synthesizes signals from:
- Policy orchestration state
- Trust guard lock status
- Policy response execution history
- Adaptive response activity
- Federation weighted consensus

Outputs unified fusion status: FUSION_GREEN / FUSION_YELLOW / FUSION_RED

This provides Tier-2 autonomous decision-making capability by combining
all subsystem signals into a single actionable fusion state.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# Paths
STATE_DIR = Path("state")
FEDERATION_DIR = Path("federation")
FORENSICS_DIR = Path("forensics")
AUDIT_FILE = Path("audit_summary.md")

POLICY_STATE = STATE_DIR / "policy_state.json"
TRUST_LOCK_STATE = Path("trust_lock_state.json")
RESPONSE_LOG = STATE_DIR / "policy_response_log.jsonl"
ADAPTIVE_RESPONSE_HISTORY = STATE_DIR / "adaptive_response_history.jsonl"
WEIGHTED_CONSENSUS = FEDERATION_DIR / "weighted_consensus.json"
SAFETY_BRAKE_STATE = FORENSICS_DIR / "safety_brake_state.json"

FUSION_STATE = STATE_DIR / "policy_fusion_state.json"
FUSION_LOG = STATE_DIR / "policy_fusion_log.jsonl"

# Thresholds
CONSENSUS_ESCALATION_THRESHOLD = 92.0  # Below this, escalate one level


def load_json(path: Path) -> Optional[Dict]:
    """Load JSON file, return None if not found."""
    if not path.exists():
        return None
    
    try:
        with path.open("r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_policy_state() -> Dict:
    """Load policy orchestration state."""
    data = load_json(POLICY_STATE)
    if not data:
        return {"policy": "GREEN", "evaluated_at": None}
    return data


def load_trust_lock_state() -> Dict:
    """Load trust guard lock state."""
    data = load_json(TRUST_LOCK_STATE)
    if not data:
        return {"locked": False}
    return data


def load_weighted_consensus() -> float:
    """Load weighted consensus percentage."""
    data = load_json(WEIGHTED_CONSENSUS)
    if not data:
        return 100.0  # Assume healthy if missing
    return data.get("weighted_consensus_pct", 100.0)


def load_safety_brake_state() -> Dict:
    """Load safety brake state from adaptive response system."""
    data = load_json(SAFETY_BRAKE_STATE)
    if not data:
        return {"is_engaged": False}
    return data


def count_recent_responses(hours: int = 24) -> int:
    """Count policy responses in last N hours."""
    if not RESPONSE_LOG.exists():
        return 0
    
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    count = 0
    
    with RESPONSE_LOG.open("r") as f:
        for line in f:
            try:
                record = json.loads(line)
                timestamp = datetime.fromisoformat(record.get("timestamp", ""))
                if timestamp >= cutoff:
                    count += 1
            except (json.JSONDecodeError, ValueError):
                continue
    
    return count


def count_adaptive_responses(hours: int = 24) -> int:
    """Count adaptive responses in last N hours."""
    if not ADAPTIVE_RESPONSE_HISTORY.exists():
        return 0
    
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    count = 0
    
    with ADAPTIVE_RESPONSE_HISTORY.open("r") as f:
        for line in f:
            try:
                record = json.loads(line)
                timestamp = datetime.fromisoformat(record.get("timestamp", ""))
                if timestamp >= cutoff:
                    count += 1
            except (json.JSONDecodeError, ValueError):
                continue
    
    return count


def compute_fusion_status() -> Dict:
    """
    Compute fusion status from all subsystem inputs.
    
    Fusion Logic:
    1. If policy = RED → FUSION_RED
    2. If safety brake active → FUSION_RED
    3. If policy = YELLOW and trust unlocked → FUSION_YELLOW
    4. If weighted consensus < 92% → escalate one level
    5. Otherwise → FUSION_GREEN
    """
    now = datetime.now(timezone.utc)
    
    # Load inputs
    policy_state = load_policy_state()
    trust_lock = load_trust_lock_state()
    consensus_pct = load_weighted_consensus()
    safety_brake = load_safety_brake_state()
    response_count_24h = count_recent_responses(24)
    adaptive_count_24h = count_adaptive_responses(24)
    
    policy = policy_state.get("policy", "GREEN")
    trust_locked = trust_lock.get("locked", False)
    brake_engaged = safety_brake.get("is_engaged", False)
    
    # Fusion decision logic
    fusion_level = "FUSION_GREEN"
    reasons = []
    
    # Rule 1: RED policy → FUSION_RED
    if policy == "RED":
        fusion_level = "FUSION_RED"
        reasons.append("policy_red")
    
    # Rule 2: Safety brake active → FUSION_RED (override)
    if brake_engaged:
        fusion_level = "FUSION_RED"
        reasons.append("safety_brake_engaged")
    
    # Rule 3: YELLOW policy + trust unlocked → FUSION_YELLOW
    if policy == "YELLOW" and not trust_locked and fusion_level != "FUSION_RED":
        fusion_level = "FUSION_YELLOW"
        reasons.append("policy_yellow_trust_unlocked")
    
    # Rule 4: Low consensus → escalate one level
    if consensus_pct < CONSENSUS_ESCALATION_THRESHOLD:
        reasons.append(f"consensus_low_{consensus_pct:.1f}%")
        if fusion_level == "FUSION_GREEN":
            fusion_level = "FUSION_YELLOW"
        elif fusion_level == "FUSION_YELLOW":
            fusion_level = "FUSION_RED"
    
    # Rule 5: Trust locked while YELLOW → escalate to RED
    if policy == "YELLOW" and trust_locked and fusion_level == "FUSION_YELLOW":
        fusion_level = "FUSION_RED"
        reasons.append("trust_locked_during_yellow")
    
    # Build fusion state
    fusion_state = {
        "fusion_level": fusion_level,
        "computed_at": now.isoformat(),
        "inputs": {
            "policy": policy,
            "policy_evaluated_at": policy_state.get("evaluated_at"),
            "trust_locked": trust_locked,
            "weighted_consensus_pct": consensus_pct,
            "safety_brake_engaged": brake_engaged,
            "policy_responses_24h": response_count_24h,
            "adaptive_responses_24h": adaptive_count_24h
        },
        "reasons": reasons,
        "thresholds": {
            "consensus_escalation": CONSENSUS_ESCALATION_THRESHOLD
        }
    }
    
    return fusion_state


def atomic_write_json(path: Path, data: Dict, retries: int = 3):
    """
    Atomic write with retry logic.
    Raises IOError on persistent failure.
    """
    import time
    
    for attempt in range(retries):
        try:
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            with tmp_path.open("w") as f:
                json.dump(data, f, indent=2)
            tmp_path.replace(path)
            return
        except (IOError, OSError) as e:
            if attempt == retries - 1:
                raise IOError(f"Failed to write {path} after {retries} attempts: {e}")
            time.sleep(1 ** (attempt + 1))  # Exponential backoff: 1s, 1s, 1s


def append_fusion_log(fusion_state: Dict):
    """Append fusion state to JSONL log."""
    STATE_DIR.mkdir(exist_ok=True)
    
    with FUSION_LOG.open("a") as f:
        f.write(json.dumps(fusion_state) + "\n")


def append_audit_marker():
    """Append idempotent audit marker to audit_summary.md."""
    if not AUDIT_FILE.exists():
        return
    
    marker_prefix = "<!-- POLICY_FUSION: UPDATED "
    timestamp = datetime.now(timezone.utc).isoformat()
    new_marker = f"{marker_prefix}{timestamp} -->"
    
    # Read full file with UTF-8 encoding and error handling
    try:
        with AUDIT_FILE.open("r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        # If still fails, skip audit marker update
        return
    
    # Remove any existing fusion markers
    lines = content.splitlines()
    filtered_lines = [line for line in lines if not line.strip().startswith(marker_prefix)]
    
    # Append new marker
    filtered_lines.append(new_marker)
    
    # Write back
    with AUDIT_FILE.open("w", encoding="utf-8") as f:
        f.write("\n".join(filtered_lines) + "\n")


def create_fix_branch(error_msg: str, fusion_state: Dict):
    """Create fix branch with diagnostic logs on persistent FS failure."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch_name = f"fix/policy-fusion-{timestamp}"
    
    # Create diagnostic log
    diagnostic = {
        "error": error_msg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fusion_state": fusion_state,
        "attempted_write": str(FUSION_STATE)
    }
    
    diagnostic_file = Path(f"logs/policy_fusion_error_{timestamp}.json")
    diagnostic_file.parent.mkdir(exist_ok=True)
    
    with diagnostic_file.open("w") as f:
        json.dump(diagnostic, f, indent=2)
    
    # Create branch and commit
    try:
        subprocess.run(["git", "checkout", "-b", branch_name], check=True, capture_output=True)
        subprocess.run(["git", "add", str(diagnostic_file)], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"fix: policy fusion FS error - {error_msg[:50]}"],
            check=True,
            capture_output=True
        )
        print(f"Created fix branch: {branch_name}", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Failed to create fix branch: {e}", file=sys.stderr)


def run_fusion_engine():
    """Main execution: compute fusion, write state, log, and audit marker."""
    try:
        # Compute fusion
        fusion_state = compute_fusion_status()
        
        # Write outputs
        try:
            STATE_DIR.mkdir(exist_ok=True)
            atomic_write_json(FUSION_STATE, fusion_state)
            append_fusion_log(fusion_state)
            append_audit_marker()
        except IOError as e:
            # Persistent FS failure → create fix branch
            create_fix_branch(str(e), fusion_state)
            raise
        
        # Print result
        print(json.dumps(fusion_state, indent=2))
        
        return 0
    
    except Exception as e:
        print(f"Error running fusion engine: {e}", file=sys.stderr)
        return 1


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Policy Fusion Engine")
    parser.add_argument("--run", action="store_true", help="Execute fusion computation")
    
    args = parser.parse_args()
    
    if args.run:
        sys.exit(run_fusion_engine())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
