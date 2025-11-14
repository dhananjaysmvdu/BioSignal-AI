#!/usr/bin/env python3
"""MV-CRS Core Challenge Verifier (Phase XXX Instruction 132)

Loads required governance and learning artifacts, performs placeholder validation
and emits a deterministic verifier result plus baseline deviation framework.

Currently NO real deviation detection is performed. The structure and persistence
pipeline is established for subsequent logic expansion.

Artifacts written/updated:
 - state/challenge_verifier_state.json (atomic write)
 - state/challenge_verifier_log.jsonl (append-only)
 - state/challenge_summary.json (baseline summary augmentation)
 - docs/audit_summary.md (idempotent MVCRS_VERIFIER marker)

Exit codes:
 0 success (status ok or warning)
 2 failed (status failed)
"""

from __future__ import annotations

import json
import os
import sys
import time
import datetime as _dt
from typing import Any, Dict, List

try:  # Support both module and script execution contexts
    from .challenge_utils import (
        atomic_write_json,
        append_jsonl,
    )
except ImportError:  # running as standalone script
    from challenge_utils import (  # type: ignore
        atomic_write_json,
        append_jsonl,
    )

MANDATORY_FILES = [
    "state/challenge_events.jsonl",
    "state/challenges_chain_meta.json",
]
OPTIONAL_FILES = [
    "federation/provenance_consensus.json",  # may be absent initially
    "state/rdgl_policy_adjustments.json",    # expected once RDGL integrated
    "state/adaptive_response_history.jsonl", # expected once adaptive response history mirrored
]
REQUIRED_FILES = MANDATORY_FILES + OPTIONAL_FILES

STATE_PATH = "state/challenge_verifier_state.json"
LOG_PATH = "state/challenge_verifier_log.jsonl"
SUMMARY_PATH = "state/challenge_summary.json"
AUDIT_SUMMARY = "docs/audit_summary.md"

DEVIATION_TYPES = [
    "TYPE_A_STRUCTURE",      # malformed/missing data
    "TYPE_B_CONSISTENCY",    # mismatch between consensus/rdgl/tuner
    "TYPE_C_FORECAST",       # prediction mismatches vs observed actions
    "TYPE_D_UNEXPECTED_ACTION",  # action/event mismatches
]

def utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def file_exists_and_nonempty(path: str) -> bool:
    return os.path.isfile(path) and os.path.getsize(path) > 0

def safe_load_json(path: str) -> Any:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def count_events(events_path: str) -> int:
    if not os.path.isfile(events_path):
        return 0
    count = 0
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count

def count_recent_events(events_path: str, days: int = 7) -> int:
    if not os.path.isfile(events_path):
        return 0
    cutoff = time.time() - days * 86400
    recent = 0
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = obj.get("ts") or obj.get("timestamp")
            if isinstance(ts, (int, float)) and ts >= cutoff:
                recent += 1
    return recent

def build_deviation_framework() -> List[Dict[str, Any]]:
    # Placeholder: empty list; structure defined for future population.
    return []

def compute_status(missing: List[str]) -> str:
    # Failure only if multiple mandatory artifacts missing
    mand_missing = [m for m in missing if m in MANDATORY_FILES]
    if len(mand_missing) >= 2:
        return "failed"
    if missing:
        return "warning"
    return "ok"

def update_audit_marker(marker_line: str) -> None:
    # Remove prior MVCRS_VERIFIER markers then append new one.
    lines: List[str] = []
    if os.path.isfile(AUDIT_SUMMARY):
        with open(AUDIT_SUMMARY, "r", encoding="utf-8") as f:
            for l in f:
                if "MVCRS_VERIFIER:" in l:
                    continue
                lines.append(l.rstrip("\n"))
    lines.append(marker_line)
    tmp = AUDIT_SUMMARY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, AUDIT_SUMMARY)

def load_all():
    artifacts = {}
    missing = []
    for path in REQUIRED_FILES:
        if not os.path.isfile(path):
            missing.append(path)
            artifacts[path] = None
            continue
        if path.endswith(".json"):
            artifacts[path] = safe_load_json(path)
        else:
            # For .jsonl or other text logs, store minimal metadata
            artifacts[path] = {"exists": True, "size": os.path.getsize(path)}
    return artifacts, missing

def update_summary(verifier_status: str) -> Dict[str, Any]:
    total_events = count_events("state/challenge_events.jsonl")
    recent_events = count_recent_events("state/challenge_events.jsonl", days=7)
    deviation_counts = {
        "TYPE_A_STRUCTURE": {"low": 0, "medium": 0, "high": 0},
        "TYPE_B_CONSISTENCY": {"low": 0, "medium": 0, "high": 0},
        "TYPE_C_FORECAST": {"low": 0, "medium": 0, "high": 0},
        "TYPE_D_UNEXPECTED_ACTION": {"low": 0, "medium": 0, "high": 0},
    }
    summary = {
        "total_events": total_events,
        "recent_window_events": recent_events,
        "deviation_counts": deviation_counts,
        "verifier_status": verifier_status,
        "last_updated": utc_iso(),
    }
    atomic_write_json(SUMMARY_PATH, summary)
    return summary

def main(argv=None) -> int:
    artifacts, missing = load_all()
    status = compute_status(missing)
    deviations = build_deviation_framework()
    result = {
        "status": status,
        "expected": {},  # placeholder
        "observed": {},  # placeholder
        "deviations": deviations,
        "missing_artifacts": missing,
        "timestamp": utc_iso(),
    }
    atomic_write_json(STATE_PATH, result)
    append_jsonl(LOG_PATH, result)
    summary = update_summary(status)
    marker = f"<!-- MVCRS_VERIFIER: UPDATED {utc_iso()} -->"
    update_audit_marker(marker)
    # Emit JSON to stdout for CI evaluation
    print(json.dumps({"result": result, "summary": summary}, separators=(",", ":")))
    return 2 if status == "failed" else 0

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
