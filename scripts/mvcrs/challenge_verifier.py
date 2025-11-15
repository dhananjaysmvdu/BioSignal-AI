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
from typing import Any, Dict, List, Tuple

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
    "federation/provenance_consensus.json",  # provenance consensus summary
    "state/rdgl_policy_adjustments.json",    # RDGL adjustments (mode, score, shift range)
    "forensics/response_history.jsonl",      # adaptive response actions
    "state/policy_fusion_state.json",        # policy fusion state
    "state/policy_state.json",               # policy state
    "state/trust_lock_state.json",           # trust lock info
]
REQUIRED_FILES = MANDATORY_FILES + OPTIONAL_FILES

STATE_PATH = "state/challenge_verifier_state.json"
LOG_PATH = "state/challenge_verifier_log.jsonl"
SUMMARY_PATH = "state/challenge_summary.json"
AUDIT_SUMMARY = "docs/audit_summary.md"

# Optional base directory override for tests/sandboxing
BASE_DIR = os.environ.get("MVCRS_BASE_DIR", "").strip()

def _p(path: str) -> str:
    return os.path.join(BASE_DIR, path) if BASE_DIR else path

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
    events_path = _p(events_path)
    if not os.path.isfile(events_path):
        return 0
    count = 0
    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count

def count_recent_events(events_path: str, days: int = 7) -> int:
    events_path = _p(events_path)
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

def _severity_from_counts(struct_corrupt: bool, mismatch_count: int, forecast_issues: int, action_conflicts: int) -> Tuple[str, Dict[str,int]]:
    if struct_corrupt or mismatch_count > 3:
        return "high", {"mismatches": mismatch_count, "forecast": forecast_issues, "actions": action_conflicts}
    if mismatch_count or forecast_issues:
        if mismatch_count <= 3 or forecast_issues > 0:
            return "medium", {"mismatches": mismatch_count, "forecast": forecast_issues, "actions": action_conflicts}
    if action_conflicts:
        return "low", {"mismatches": mismatch_count, "forecast": forecast_issues, "actions": action_conflicts}
    return "low", {"mismatches": mismatch_count, "forecast": forecast_issues, "actions": action_conflicts}

def build_deviations(artifacts: Dict[str, Any], missing: List[str]) -> List[Dict[str, Any]]:
    deviations: List[Dict[str, Any]] = []
    ts_now = utc_iso()
    struct_corrupt = False

    # TYPE_A_STRUCTURE: missing artifacts & JSONL corruption
    for m in missing:
        if m in MANDATORY_FILES:
            deviations.append({
                "type": "TYPE_A_STRUCTURE",
                "severity": "high",
                "metric": "artifact_presence",
                "expected": "present",
                "observed": "missing",
                "details": {"path": m},
                "timestamp": ts_now,
            })
            struct_corrupt = True
        else:
            deviations.append({
                "type": "TYPE_A_STRUCTURE",
                "severity": "low",
                "metric": "artifact_presence",
                "expected": "present",
                "observed": "missing",
                "details": {"path": m},
                "timestamp": ts_now,
            })

    events_path = _p("state/challenge_events.jsonl")
    if os.path.isfile(events_path):
        with open(events_path, "r", encoding="utf-8") as f:
            line_no = 0
            for raw in f:
                line_no += 1
                ln = raw.strip()
                if not ln:
                    continue
                try:
                    json.loads(ln)
                except json.JSONDecodeError as e:
                    deviations.append({
                        "type": "TYPE_A_STRUCTURE",
                        "severity": "high",
                        "metric": "jsonl_integrity",
                        "expected": "valid_json",
                        "observed": "parse_error",
                        "details": {"line": line_no, "error": str(e)},
                        "timestamp": utc_iso(),
                    })
                    struct_corrupt = True

    # TYPE_B_CONSISTENCY: simplified placeholder checks
    mismatch_count = 0
    rdgl = artifacts.get("state/rdgl_policy_adjustments.json")
    fusion = artifacts.get("state/policy_fusion_state.json")
    policy_state = artifacts.get("state/policy_state.json")
    if rdgl and isinstance(rdgl, dict) and fusion and isinstance(fusion, dict):
        rdgl_mode = rdgl.get("mode")
        fusion_policy = fusion.get("inputs", {}).get("policy")
        if rdgl_mode and fusion_policy and rdgl_mode.lower().startswith("locked") and fusion_policy != "RED":
            deviations.append({
                "type": "TYPE_B_CONSISTENCY",
                "severity": "medium",
                "metric": "rdgl_mode_vs_policy",
                "expected": "policy RED when rdgl locked",
                "observed": f"policy {fusion_policy} with rdgl_mode {rdgl_mode}",
                "details": {},
                "timestamp": utc_iso(),
            })
            mismatch_count += 1
    if fusion and isinstance(fusion, dict):
        consensus_pct = fusion.get("inputs", {}).get("weighted_consensus_pct")
        if isinstance(consensus_pct, (int, float)) and consensus_pct < 90:
            deviations.append({
                "type": "TYPE_B_CONSISTENCY",
                "severity": "medium",
                "metric": "weighted_consensus_pct",
                "expected": ">=90",
                "observed": consensus_pct,
                "details": {},
                "timestamp": utc_iso(),
            })
            mismatch_count += 1

    # TYPE_C_FORECAST
    forecast_issues = 0
    if policy_state and isinstance(policy_state, dict):
        risk = policy_state.get("inputs", {}).get("forecast_risk")
        responses_24h = policy_state.get("inputs", {}).get("recent_responses")
        if risk == "high" and isinstance(responses_24h, int) and responses_24h < 2:
            deviations.append({
                "type": "TYPE_C_FORECAST",
                "severity": "medium",
                "metric": "high_risk_low_responses",
                "expected": "responsive_actions>=2",
                "observed": responses_24h,
                "details": {"risk": risk},
                "timestamp": utc_iso(),
            })
            forecast_issues += 1
        if risk == "low" and isinstance(responses_24h, int) and responses_24h > 5:
            deviations.append({
                "type": "TYPE_C_FORECAST",
                "severity": "medium",
                "metric": "low_risk_high_responses",
                "expected": "responses<=5",
                "observed": responses_24h,
                "details": {"risk": risk},
                "timestamp": utc_iso(),
            })
            forecast_issues += 1

    # TYPE_D_UNEXPECTED_ACTION
    action_conflicts = 0
    trust_lock = artifacts.get("state/trust_lock_state.json")
    responses_log_path = _p("forensics/response_history.jsonl")
    if trust_lock and isinstance(trust_lock, dict) and trust_lock.get("locked") is True and os.path.isfile(responses_log_path):
        with open(responses_log_path, "r", encoding="utf-8") as f:
            for raw in f:
                ln = raw.strip()
                if not ln:
                    continue
                try:
                    obj = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if obj.get("event_type") == "ADAPTIVE_RESPONSE":
                    deviations.append({
                        "type": "TYPE_D_UNEXPECTED_ACTION",
                        "severity": "medium",
                        "metric": "action_during_trust_lock",
                        "expected": "no_adaptive_response",
                        "observed": obj.get("status"),
                        "details": {"response_id": obj.get("response_id")},
                        "timestamp": utc_iso(),
                    })
                    action_conflicts += 1

    aggregate_severity, _agg_details = _severity_from_counts(struct_corrupt, mismatch_count, forecast_issues, action_conflicts)
    if aggregate_severity == "high":
        for d in deviations:
            if d["severity"] in ("medium", "low") and d["type"] != "TYPE_D_UNEXPECTED_ACTION":
                d["severity"] = "high"
    elif aggregate_severity == "medium":
        for d in deviations:
            if d["severity"] == "low" and d["type"] != "TYPE_D_UNEXPECTED_ACTION":
                d["severity"] = "medium"
    return deviations

def compute_status_from_deviations(devs: List[Dict[str, Any]]) -> str:
    if any(d["severity"] == "high" for d in devs):
        return "failed"
    if any(d["severity"] == "medium" for d in devs):
        return "warning"
    return "ok"

def update_audit_marker(marker_line: str, escalation_marker: str | None = None) -> None:
    lines: List[str] = []
    audit_path = _p(AUDIT_SUMMARY)
    if os.path.isfile(audit_path):
        with open(audit_path, "r", encoding="utf-8") as f:
            for l in f:
                if "MVCRS_VERIFIER:" in l or "MVCRS_ESCALATION:" in l:
                    continue
                lines.append(l.rstrip("\n"))
    lines.append(marker_line)
    if escalation_marker:
        lines.append(escalation_marker)
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    tmp = audit_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, audit_path)

def load_all():
    artifacts = {}
    missing = []
    for path in REQUIRED_FILES:
        rp = _p(path)
        if not os.path.isfile(rp):
            missing.append(path)
            artifacts[path] = None
            continue
        if path.endswith(".json"):
            artifacts[path] = safe_load_json(rp)
        else:
            artifacts[path] = {"exists": True, "size": os.path.getsize(rp)}
    return artifacts, missing

def update_summary(verifier_status: str, deviations: List[Dict[str, Any]], escalation_created: bool, escalation_ts: str | None) -> Dict[str, Any]:
    total_events = count_events("state/challenge_events.jsonl")
    recent_events = count_recent_events("state/challenge_events.jsonl", days=7)
    deviation_counts = {t: {"low": 0, "medium": 0, "high": 0} for t in DEVIATION_TYPES}
    severity_totals = {"low": 0, "medium": 0, "high": 0}
    for d in deviations:
        deviation_counts[d["type"]][d["severity"]] += 1
        severity_totals[d["severity"]] += 1
    summary = {
        "total_events": total_events,
        "recent_window_events": recent_events,
        "deviation_counts": deviation_counts,
        "severity_totals": severity_totals,
        "verifier_status": verifier_status,
        "escalation_triggered": escalation_created,
        "last_escalation_ts": escalation_ts,
        "last_updated": utc_iso(),
    }
    atomic_write_json(_p(SUMMARY_PATH), summary)
    return summary

def create_escalation(deviations: List[Dict[str, Any]], artifacts: Dict[str, Any]) -> Dict[str, Any]:
    high_devs = [d for d in deviations if d["severity"] == "high"]
    ts = utc_iso()
    recommended = "force_response_review"
    types = {d["type"] for d in high_devs}
    if any(t == "TYPE_A_STRUCTURE" for t in types):
        recommended = "trigger_self_healing"
    elif any(t == "TYPE_B_CONSISTENCY" for t in types):
        recommended = "force_threshold_recompute"
    elif any(t in {"TYPE_C_FORECAST", "TYPE_D_UNEXPECTED_ACTION"} for t in types):
        recommended = "force_response_review"
    payload = {
        "id": f"escalation-{ts.replace(':','').replace('-','')}",
        "timestamp": ts,
        "recommended_action": recommended,
        "high_severity_deviations": high_devs,
        "snapshot": {"artifact_keys": list(artifacts.keys())},
    }
    atomic_write_json(_p("state/mvcrs_escalation.json"), payload)
    return payload

def main(argv=None) -> int:
    artifacts, missing = load_all()
    deviations = build_deviations(artifacts, missing)
    status = compute_status_from_deviations(deviations)
    escalation_payload = None
    escalation_marker = None
    escalation_ts = None
    if status == "failed":
        escalation_payload = create_escalation(deviations, artifacts)
        escalation_ts = escalation_payload["timestamp"]
        escalation_marker = f"<!-- MVCRS_ESCALATION: CREATED {escalation_ts} -->"
    result = {
        "status": status,
        "expected": {},
        "observed": {},
        "deviations": deviations,
        "missing_artifacts": missing,
        "timestamp": utc_iso(),
    }
    atomic_write_json(_p(STATE_PATH), result)
    append_jsonl(_p(LOG_PATH), result)
    summary = update_summary(status, deviations, escalation_payload is not None, escalation_ts)
    marker = f"<!-- MVCRS_VERIFIER: UPDATED {utc_iso()} -->"
    update_audit_marker(marker, escalation_marker)
    output = {"result": result, "summary": summary, "escalation": escalation_payload}
    print(json.dumps(output, separators=(",", ":")))
    return 2 if status == "failed" else 0

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
