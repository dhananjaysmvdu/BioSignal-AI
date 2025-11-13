#!/usr/bin/env python3
"""
Policy Provenance Tracker

Compares governance_policy.json between commits/releases and generates a semantic
diff timeline showing how governance coefficients, thresholds, and regime policies
evolve over the project lifecycle.

Outputs:
- exports/policy_evolution_timeline.csv (longitudinal changes)
- Appends entries to exports/schema_provenance_ledger.jsonl
- Updates GOVERNANCE_TRANSPARENCY.md with policy evolution summary

This enables research on "governance policy as code" version control.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "configs" / "governance_policy.json"
TIMELINE_PATH = ROOT / "exports" / "policy_evolution_timeline.csv"
LEDGER_PATH = ROOT / "exports" / "schema_provenance_ledger.jsonl"


@dataclass
class PolicySnapshot:
    """Represents a policy state at a specific point in time."""
    timestamp: str
    commit_sha: str
    tag: Optional[str]
    policy_hash: str
    policy_data: Dict[str, Any]
    changes: List[str] = field(default_factory=list)


def _run_git(args: List[str]) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git not found"


def _get_commits_touching_policy() -> List[Tuple[str, str, Optional[str]]]:
    """Return list of (commit_sha, iso_timestamp, tag_if_any) for policy file."""
    code, out, _ = _run_git([
        "log", "--follow", "--pretty=format:%H|%cI", "--", str(POLICY_PATH.relative_to(ROOT))
    ])
    if code != 0 or not out:
        return []
    
    commits = []
    for line in out.splitlines():
        if "|" not in line:
            continue
        sha, ts = line.split("|", 1)
        # Check if commit has a tag
        code_tag, tag_out, _ = _run_git(["describe", "--tags", "--exact-match", sha])
        tag = tag_out if code_tag == 0 else None
        commits.append((sha, ts, tag))
    
    return commits


def _get_policy_at_commit(commit_sha: str) -> Optional[Dict[str, Any]]:
    """Retrieve governance_policy.json content at a specific commit."""
    code, out, _ = _run_git([
        "show", f"{commit_sha}:{POLICY_PATH.relative_to(ROOT)}"
    ])
    if code != 0:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def _compute_hash(data: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of policy JSON (canonical serialization)."""
    canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _compare_policies(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    """Generate semantic diff descriptions between two policy versions."""
    changes = []
    
    # Helper to recursively compare nested dicts
    def _diff_dict(path: str, old_d: Any, new_d: Any) -> None:
        if not isinstance(old_d, dict) or not isinstance(new_d, dict):
            if old_d != new_d:
                changes.append(f"{path}: {old_d} → {new_d}")
            return
        
        all_keys = set(old_d.keys()) | set(new_d.keys())
        for key in sorted(all_keys):
            new_path = f"{path}.{key}" if path else key
            if key not in old_d:
                changes.append(f"{new_path}: added ({new_d[key]})")
            elif key not in new_d:
                changes.append(f"{new_path}: removed (was {old_d[key]})")
            elif isinstance(old_d[key], dict) and isinstance(new_d[key], dict):
                _diff_dict(new_path, old_d[key], new_d[key])
            elif old_d[key] != new_d[key]:
                changes.append(f"{new_path}: {old_d[key]} → {new_d[key]}")
    
    _diff_dict("", old, new)
    return changes


def _build_timeline() -> List[PolicySnapshot]:
    """Construct chronological timeline of policy changes."""
    commits = _get_commits_touching_policy()
    if not commits:
        return []
    
    snapshots: List[PolicySnapshot] = []
    prev_data: Optional[Dict[str, Any]] = None
    
    # Process in chronological order (oldest first)
    for sha, ts, tag in reversed(commits):
        policy_data = _get_policy_at_commit(sha)
        if policy_data is None:
            continue
        
        policy_hash = _compute_hash(policy_data)
        changes_list: List[str] = []
        
        if prev_data is not None:
            changes_list = _compare_policies(prev_data, policy_data)
        else:
            changes_list = ["Initial policy baseline"]
        
        # Only record if there are actual changes or it's the first snapshot
        if changes_list:
            snapshots.append(PolicySnapshot(
                timestamp=ts,
                commit_sha=sha[:7],
                tag=tag,
                policy_hash=policy_hash,
                policy_data=policy_data,
                changes=changes_list
            ))
            prev_data = policy_data
    
    return snapshots


def _write_timeline_csv(snapshots: List[PolicySnapshot]) -> None:
    """Write policy evolution to CSV."""
    TIMELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with TIMELINE_PATH.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "commit_sha", "tag", "policy_hash", "num_changes", "changes_summary"
        ])
        
        for snap in snapshots:
            changes_summary = "; ".join(snap.changes[:3])  # First 3 for readability
            if len(snap.changes) > 3:
                changes_summary += f" (+{len(snap.changes) - 3} more)"
            
            writer.writerow([
                snap.timestamp,
                snap.commit_sha,
                snap.tag or "",
                snap.policy_hash,
                len(snap.changes),
                changes_summary
            ])


def _append_to_ledger(snapshots: List[PolicySnapshot]) -> None:
    """Append policy snapshots to provenance ledger."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing entries to avoid duplicates
    existing_hashes = set()
    if LEDGER_PATH.exists():
        try:
            with LEDGER_PATH.open('r', encoding='utf-8') as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("event_type") == "policy_change":
                        existing_hashes.add(entry.get("policy_hash"))
        except Exception:
            pass
    
    # Append new snapshots
    with LEDGER_PATH.open('a', encoding='utf-8') as f:
        for snap in snapshots:
            if snap.policy_hash in existing_hashes:
                continue
            
            entry = {
                "timestamp": snap.timestamp,
                "event_type": "policy_change",
                "commit_sha": snap.commit_sha,
                "tag": snap.tag,
                "policy_hash": snap.policy_hash,
                "num_changes": len(snap.changes),
                "changes": snap.changes
            }
            f.write(json.dumps(entry) + "\n")
            existing_hashes.add(snap.policy_hash)


def _update_transparency_manifest(num_snapshots: int) -> None:
    """Add policy evolution summary to transparency manifest."""
    manifest_path = ROOT / "GOVERNANCE_TRANSPARENCY.md"
    if not manifest_path.exists():
        return
    
    try:
        content = manifest_path.read_text(encoding='utf-8')
        
        # Find insertion point (after "API Endpoints" section)
        marker = "## Citation & Research Export"
        if marker not in content:
            return
        
        summary_block = f"""
## Policy Evolution Timeline

Policy versions tracked: {num_snapshots}  
Latest timeline: `exports/policy_evolution_timeline.csv`  
Full provenance: `exports/schema_provenance_ledger.jsonl` (event_type: policy_change)

The governance policy has evolved {num_snapshots} times since project inception, with all changes cryptographically tracked in the provenance ledger. This enables semantic version control for AI governance parameters.

"""
        
        # Insert before citation block if not already present
        if "## Policy Evolution Timeline" not in content:
            content = content.replace(marker, summary_block + marker)
            manifest_path.write_text(content, encoding='utf-8')
    except Exception:
        pass


def main() -> int:
    print("Analyzing governance policy evolution...")
    
    snapshots = _build_timeline()
    
    if not snapshots:
        print("No policy changes found in git history")
        return 0
    
    print(f"Found {len(snapshots)} policy snapshots:")
    for snap in snapshots:
        tag_info = f" (tag: {snap.tag})" if snap.tag else ""
        print(f"  {snap.timestamp} [{snap.commit_sha}]{tag_info}: {len(snap.changes)} changes")
    
    # Write outputs
    _write_timeline_csv(snapshots)
    print(f"Timeline written: {TIMELINE_PATH}")
    
    _append_to_ledger(snapshots)
    print(f"Ledger updated: {LEDGER_PATH}")
    
    _update_transparency_manifest(len(snapshots))
    print("Transparency manifest updated")
    
    # Print summary statistics
    total_changes = sum(len(s.changes) for s in snapshots)
    print(f"\nSummary:")
    print(f"  Total policy versions: {len(snapshots)}")
    print(f"  Total semantic changes: {total_changes}")
    print(f"  Average changes per version: {total_changes / len(snapshots):.1f}")
    
    if snapshots:
        latest = snapshots[-1]
        print(f"  Latest policy hash: {latest.policy_hash}")
        print(f"  Latest commit: {latest.commit_sha}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
