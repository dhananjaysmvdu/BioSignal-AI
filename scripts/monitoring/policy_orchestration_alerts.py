#!/usr/bin/env python3
"""
Policy Orchestration Monitoring & Alerts

Monitors policy state changes and generates alerts for critical conditions:
- Policy flips to RED > 2 times in 24h
- Safety brake engaged for > 4 hours
- Response runner blocked > 3 consecutive times
- Fix branches created from policy failures

Outputs:
- reports/policy_orchestration_alerts.json
- logs/policy_orchestration_alerts.jsonl
- audit_summary.md markers: <!-- POLICY_ALERT: CREATED <timestamp> reason: <text> -->
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Alert thresholds
POLICY_RED_FLIP_THRESHOLD = 2  # per 24h
SAFETY_BRAKE_DURATION_THRESHOLD_HOURS = 4
RESPONSE_BLOCKED_CONSECUTIVE_THRESHOLD = 3
FIX_BRANCH_ALERT_ENABLED = True

# Paths
STATE_DIR = Path("state")
LOGS_DIR = Path("logs")
REPORTS_DIR = Path("reports")
FORENSICS_DIR = Path("forensics")
AUDIT_FILE = Path("audit_summary.md")

POLICY_STATE_LOG = STATE_DIR / "policy_state_log.jsonl"
RESPONSE_LOG = STATE_DIR / "policy_response_log.jsonl"
SAFETY_BRAKE_STATE = FORENSICS_DIR / "safety_brake_state.json"
ALERTS_REPORT = REPORTS_DIR / "policy_orchestration_alerts.json"
ALERTS_LOG = LOGS_DIR / "policy_orchestration_alerts.jsonl"


def load_jsonl(path: Path, hours: int = 24) -> List[Dict]:
    """Load JSONL records from last N hours."""
    if not path.exists():
        return []
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    records = []
    
    with path.open("r") as f:
        for line in f:
            try:
                record = json.loads(line)
                timestamp = datetime.fromisoformat(record.get("timestamp", record.get("evaluated_at", "")))
                if timestamp >= cutoff:
                    records.append(record)
            except (json.JSONDecodeError, ValueError):
                continue
    
    return records


def count_policy_red_flips(hours: int = 24) -> int:
    """Count how many times policy flipped to RED in last N hours."""
    records = load_jsonl(POLICY_STATE_LOG, hours)
    
    red_count = 0
    prev_policy = None
    
    for record in records:
        current_policy = record.get("policy")
        if current_policy == "RED" and prev_policy != "RED":
            red_count += 1
        prev_policy = current_policy
    
    return red_count


def check_safety_brake_duration() -> Optional[float]:
    """Check if safety brake has been engaged for too long. Returns hours engaged."""
    if not SAFETY_BRAKE_STATE.exists():
        return None
    
    with SAFETY_BRAKE_STATE.open("r") as f:
        state = json.load(f)
    
    if not state.get("is_engaged"):
        return None
    
    last_check = datetime.fromisoformat(state.get("last_check", ""))
    now = datetime.now(timezone.utc)
    hours_engaged = (now - last_check).total_seconds() / 3600
    
    return hours_engaged


def count_consecutive_blocked_responses() -> int:
    """Count consecutive blocked response attempts."""
    records = load_jsonl(RESPONSE_LOG, hours=48)
    
    if not records:
        return 0
    
    # Sort by timestamp descending (most recent first)
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    
    consecutive = 0
    for record in records:
        if record.get("blocked") or record.get("actions_succeeded", 1) == 0:
            consecutive += 1
        else:
            break  # Stop at first successful execution
    
    return consecutive


def check_recent_fix_branches() -> List[str]:
    """Check for fix branches created in last 24h (via git log)."""
    import subprocess
    
    try:
        result = subprocess.run(
            ["git", "branch", "--list", "fix/policy-*", "fix/response-*"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        branches = [b.strip().lstrip("* ") for b in result.stdout.splitlines()]
        return branches
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def generate_alerts() -> Dict:
    """Generate alert report based on monitoring checks."""
    now = datetime.now(timezone.utc)
    alerts = []
    
    # Check 1: Policy RED flips
    red_flips = count_policy_red_flips(24)
    if red_flips > POLICY_RED_FLIP_THRESHOLD:
        alerts.append({
            "type": "policy_red_frequent",
            "severity": "high",
            "message": f"Policy flipped to RED {red_flips} times in 24h (threshold: {POLICY_RED_FLIP_THRESHOLD})",
            "count": red_flips,
            "threshold": POLICY_RED_FLIP_THRESHOLD,
            "action": "Review policy thresholds and subsystem health"
        })
    
    # Check 2: Safety brake duration
    brake_hours = check_safety_brake_duration()
    if brake_hours and brake_hours > SAFETY_BRAKE_DURATION_THRESHOLD_HOURS:
        alerts.append({
            "type": "safety_brake_prolonged",
            "severity": "critical",
            "message": f"Safety brake engaged for {brake_hours:.1f} hours (threshold: {SAFETY_BRAKE_DURATION_THRESHOLD_HOURS}h)",
            "hours_engaged": brake_hours,
            "threshold": SAFETY_BRAKE_DURATION_THRESHOLD_HOURS,
            "action": "Manual investigation required - reset brake if resolved"
        })
    
    # Check 3: Consecutive blocked responses
    blocked_count = count_consecutive_blocked_responses()
    if blocked_count >= RESPONSE_BLOCKED_CONSECUTIVE_THRESHOLD:
        alerts.append({
            "type": "response_blocked_consecutive",
            "severity": "medium",
            "message": f"Response runner blocked {blocked_count} consecutive times (threshold: {RESPONSE_BLOCKED_CONSECUTIVE_THRESHOLD})",
            "count": blocked_count,
            "threshold": RESPONSE_BLOCKED_CONSECUTIVE_THRESHOLD,
            "action": "Check safety gates: trust lock, safety brake, rate limit"
        })
    
    # Check 4: Fix branches
    if FIX_BRANCH_ALERT_ENABLED:
        fix_branches = check_recent_fix_branches()
        if fix_branches:
            alerts.append({
                "type": "fix_branches_created",
                "severity": "medium",
                "message": f"Found {len(fix_branches)} fix branch(es) from policy/response failures",
                "branches": fix_branches,
                "action": "Review fix branch logs and resolve underlying issues"
            })
    
    report = {
        "generated_at": now.isoformat(),
        "alert_count": len(alerts),
        "alerts": alerts
    }
    
    return report


def append_audit_marker(alert: Dict):
    """Append alert marker to audit_summary.md."""
    if not AUDIT_FILE.exists():
        return
    
    marker = f'<!-- POLICY_ALERT: CREATED {datetime.now(timezone.utc).isoformat()} type: {alert["type"]} severity: {alert["severity"]} -->'
    
    with AUDIT_FILE.open("a") as f:
        f.write(f"\n{marker}\n")


def write_alert_log(report: Dict):
    """Append alert report to JSONL log."""
    LOGS_DIR.mkdir(exist_ok=True)
    
    with ALERTS_LOG.open("a") as f:
        f.write(json.dumps(report) + "\n")


def write_alert_report(report: Dict):
    """Write current alert report."""
    REPORTS_DIR.mkdir(exist_ok=True)
    
    with ALERTS_REPORT.open("w") as f:
        json.dump(report, f, indent=2)


def main():
    """Main execution: generate alerts and write outputs."""
    report = generate_alerts()
    
    # Write outputs
    write_alert_report(report)
    write_alert_log(report)
    
    # Append audit markers for each alert
    for alert in report.get("alerts", []):
        append_audit_marker(alert)
    
    # Print summary
    print(json.dumps(report, indent=2))
    
    # Exit with code 1 if any high/critical alerts
    has_critical = any(a["severity"] in ["high", "critical"] for a in report.get("alerts", []))
    sys.exit(1 if has_critical else 0)


if __name__ == "__main__":
    main()
