#!/usr/bin/env python3
"""MV-CRS Correction Engine (Instruction 135)

Closes the governance loop by applying soft / hard correction actions
based on verifier output & escalation metadata.

Behaviours:
  - No-op if verifier status = ok
  - Soft corrections if status = warning
  - Hard + Soft corrections if status = failed (subject to trust lock / safety brake / rate limits)

Artifacts consumed:
  - state/challenge_verifier_state.json
  - state/mvcrs_escalation.json (optional)
  - state/trust_lock_state.json (optional)
  - state/safety_brake_state.json (optional)
  - state/mvcrs_correction_profile.json (auto-created if missing)

Artifacts produced:
  - state/mvcrs_correction_log.jsonl (append-only)
  - state/mvcrs_last_correction.json (latest correction summary)
  - Updated state/policy_fusion_state.json, federation/provenance_bundle.json etc (simulated)
  - Updated docs/audit_summary.md with idempotent MVCRS_CORRECTION marker
  - challenge_summary.json merged with correction metadata

Environment:
  - MVCRS_BASE_DIR: optional sandbox prefix (used in tests)
  - MVCRS_FORCE_CORRECTION_FS_FAILURE=1 forces simulated persistent FS error (branch creation path)
  - MVCRS_FAST_TEST=1 skips retry sleep delays

Rate limiting:
  - At most profile.daily_hard_correction_limit hard corrections per 24h window

Exit codes:
  0 success / no-op / soft-only
  3 hard corrections applied
  4 correction attempted but blocked (trust lock / safety brake / rate limit)
  7 persistent failure triggering fix branch
"""

from __future__ import annotations

import json, os, sys, time, datetime as _dt, hashlib, subprocess
from typing import Any, Dict, List

BASE_DIR = os.environ.get("MVCRS_BASE_DIR", "").strip()

def _p(path: str) -> str:
    base = os.environ.get("MVCRS_BASE_DIR", BASE_DIR).strip()
    return os.path.join(base, path) if base else path

def path(rel: str) -> str:
    return _p(rel)

def utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def atomic_write_json_retry(path: str, data: Any, attempts: int = 3) -> None:
    delay_seq = [1,3,9]
    fast = os.environ.get("MVCRS_FAST_TEST") == "1"
    for i in range(attempts):
        tmp = path + f".tmp-{os.getpid()}-{i}"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",",":"))
            os.replace(tmp, path)
            return
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            if i == attempts - 1:
                raise
            if not fast:
                time.sleep(delay_seq[i])

def append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, separators=(",",":")) + "\n")

def load_json(path: str) -> Any:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def ensure_profile() -> Dict[str, Any]:
    prof = load_json(path("state/mvcrs_correction_profile.json"))
    if prof:
        return prof
    prof = {
        "allowed_soft_actions": {
            "regenerate_summary": True,
            "refresh_provenance_bundle": True,
            "recompute_weighted_consensus": True,
            "schema_enforcement": True,
        },
        "allowed_hard_actions": {
            "trigger_self_healing_kernel": True,
            "rebuild_integrity_anchor": True,
            "force_threshold_recompute": True,
            "force_rdgl_policy_adjustments": True,
        },
        "manual_approval_required_for_hard_actions": True,
        "daily_hard_correction_limit": 5,
        "last_reset": utc_iso(),
    }
    atomic_write_json_retry(path("state/mvcrs_correction_profile.json"), prof)
    return prof

def count_recent_hard_corrections(window_hours: int = 24) -> int:
    if not os.path.isfile(path("state/mvcrs_correction_log.jsonl")):
        return 0
    cutoff = time.time() - window_hours * 3600
    cnt = 0
    with open(path("state/mvcrs_correction_log.jsonl"), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("action_scope") == "hard":
                ts = obj.get("timestamp")
                try:
                    t = _dt.datetime.fromisoformat(ts.replace("Z","+00:00"))
                    if t.timestamp() >= cutoff:
                        cnt += 1
                except Exception:
                    continue
    return cnt

def write_audit_marker(ts: str, status: str) -> None:
    # status: UPDATED | FAILED
    lines: List[str] = []
    audit_path = path("docs/audit_summary.md")
    if os.path.isfile(audit_path):
        with open(audit_path, "r", encoding="utf-8") as f:
            for l in f:
                if "MVCRS_CORRECTION:" in l:
                    continue
                lines.append(l.rstrip("\n"))
    marker = f"<!-- MVCRS_CORRECTION: {status} {ts} -->"
    lines.append(marker)
    tmp = audit_path + ".tmp"
    os.makedirs(os.path.dirname(audit_path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, audit_path)

def merge_summary(correction_summary: Dict[str, Any]) -> None:
    existing = load_json(path("state/challenge_summary.json")) or {}
    existing.update({
        "correction_type": correction_summary.get("correction_type"),
        "hard_count_24h": correction_summary.get("hard_count_24h"),
        "blocked_by_trust_lock": correction_summary.get("blocked_by_trust_lock"),
        "blocked_by_safety_brake": correction_summary.get("blocked_by_safety_brake"),
        "last_correction_ts": correction_summary.get("timestamp"),
    })
    atomic_write_json_retry(path("state/challenge_summary.json"), existing)

def soft_actions(profile: Dict[str,bool]) -> List[Dict[str, Any]]:
    actions_executed = []
    ts = utc_iso()
    # Regenerate summary (simulate by tagging last_regenerated field)
    if profile.get("regenerate_summary"):
        summ = load_json(path("state/challenge_summary.json")) or {}
        summ["summary_regenerated_at"] = ts
        atomic_write_json_retry(path("state/challenge_summary.json"), summ)
        actions_executed.append({"name":"regenerate_summary","undo":"restore previous summary","timestamp":ts})
    # Refresh provenance bundle (simulate new hash)
    if profile.get("refresh_provenance_bundle"):
        bundle = {"timestamp": ts, "hash": hashlib.sha256(ts.encode()).hexdigest()}
        atomic_write_json_retry(path("federation/provenance_bundle.json"), bundle)
        actions_executed.append({"name":"refresh_provenance_bundle","undo":"delete bundle file","timestamp":ts})
    # Recompute weighted consensus (simulate update)
    if profile.get("recompute_weighted_consensus"):
        fusion = load_json(path("state/policy_fusion_state.json")) or {"inputs": {}}
        fusion.setdefault("inputs", {})["weighted_consensus_pct"] = 95.0
        fusion["computed_at"] = ts
        atomic_write_json_retry(path("state/policy_fusion_state.json"), fusion)
        actions_executed.append({"name":"recompute_weighted_consensus","undo":"restore previous fusion state","timestamp":ts})
    # Schema enforcement (simulate artifact check result)
    if profile.get("schema_enforcement"):
        enforcement = {"timestamp": ts, "status": "clean", "checked": ["challenge_events","policy_state","fusion_state"]}
        atomic_write_json_retry(path("state/schema_enforcement_report.json"), enforcement)
        actions_executed.append({"name":"schema_enforcement","undo":"archive enforcement report","timestamp":ts})
    return actions_executed

def hard_actions(profile: Dict[str,bool]) -> List[Dict[str, Any]]:
    actions_executed = []
    ts = utc_iso()
    if profile.get("trigger_self_healing_kernel"):
        atomic_write_json_retry(path("state/self_healing_kernel_trigger.json"), {"triggered_at": ts, "status":"queued"})
        actions_executed.append({"name":"trigger_self_healing_kernel","undo":"revert kernel trigger","timestamp":ts})
    if profile.get("rebuild_integrity_anchor"):
        anchor = {"rebuilt_at": ts, "anchor_hash": hashlib.sha256((ts+"anchor").encode()).hexdigest()}
        atomic_write_json_retry(path("state/integrity_anchor.json"), anchor)
        actions_executed.append({"name":"rebuild_integrity_anchor","undo":"restore previous anchor","timestamp":ts})
    if profile.get("force_threshold_recompute"):
        thresh = load_json(path("state/threshold_policy.json")) or {}
        thresh["last_recompute"] = ts
        atomic_write_json_retry(path("state/threshold_policy.json"), thresh)
        actions_executed.append({"name":"force_threshold_recompute","undo":"restore previous threshold policy","timestamp":ts})
    if profile.get("force_rdgl_policy_adjustments"):
        rdgl = load_json(path("state/rdgl_policy_adjustments.json")) or {}
        rdgl["mode"] = "adaptive"
        rdgl["last_adjusted"] = ts
        atomic_write_json_retry(path("state/rdgl_policy_adjustments.json"), rdgl)
        actions_executed.append({"name":"force_rdgl_policy_adjustments","undo":"restore previous rdgl policy","timestamp":ts})
    return actions_executed

def create_fix_branch() -> str:
    ts = utc_iso().replace(':','').replace('-','')
    branch_name = f"fix/mvcrs-correction-{ts}"
    # Attempt git branch creation in repository root (BASE_DIR may not be repo)
    try:
        subprocess.run(["git","rev-parse","--is-inside-work-tree"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git","checkout","-b", branch_name], check=True)
    except Exception:
        # Fallback marker file
        atomic_write_json_retry(path(f"state/{branch_name.replace('/','_')}.json"), {"created_at": utc_iso()})
    return branch_name

def main(argv=None) -> int:
    # Refresh BASE_DIR at runtime for tests that set env after import
    global BASE_DIR
    BASE_DIR = os.environ.get("MVCRS_BASE_DIR", BASE_DIR).strip()
    verifier_state = load_json(path("state/challenge_verifier_state.json"))
    if not verifier_state:
        print(json.dumps({"error":"verifier_state_missing"}))
        return 7
    status = verifier_state.get("status", "ok")
    profile_all = ensure_profile()
    soft_profile = profile_all.get("allowed_soft_actions", {})
    hard_profile = profile_all.get("allowed_hard_actions", {})
    trust_lock = load_json(path("state/trust_lock_state.json")) or {}
    safety_brake = load_json(path("state/safety_brake_state.json")) or {}
    trust_locked = bool(trust_lock.get("locked"))
    brake_engaged = bool(safety_brake.get("engaged") or safety_brake.get("is_engaged"))
    recent_hard = count_recent_hard_corrections()
    hard_limit = int(profile_all.get("daily_hard_correction_limit",5))

    force_fail = os.environ.get("MVCRS_FORCE_CORRECTION_FS_FAILURE") == "1"

    correction_type = "none"
    actions_soft: List[Dict[str,Any]] = []
    actions_hard: List[Dict[str,Any]] = []
    blocked_flags = {
        "blocked_by_trust_lock": False,
        "blocked_by_safety_brake": False,
        "blocked_by_rate_limit": False,
    }
    exit_code = 0

    if status == "ok":
        # No-op
        output = {"correction_type": correction_type, "timestamp": utc_iso(), "hard_count_24h": recent_hard, **blocked_flags}
        print(json.dumps({"result":output}, separators=(",",":")))
        return exit_code

    # Soft corrections allowed for warning/failed
    actions_soft = soft_actions(soft_profile)
    correction_type = "soft"
    exit_code = 0

    if status == "failed":
        # Evaluate hard corrections eligibility
        if trust_locked:
            blocked_flags["blocked_by_trust_lock"] = True
        if brake_engaged:
            blocked_flags["blocked_by_safety_brake"] = True
        if recent_hard >= hard_limit:
            blocked_flags["blocked_by_rate_limit"] = True
        if any(blocked_flags.values()):
            correction_type = "soft_blocked"
            exit_code = 4
        else:
            actions_hard = hard_actions(hard_profile)
            correction_type = "hard"
            exit_code = 3

    # Simulated persistent failure triggering fix branch
    branch_name = None
    if force_fail and correction_type in {"hard","soft_blocked"}:
        try:
            raise IOError("Simulated filesystem failure")
        except Exception:
            branch_name = create_fix_branch()
            write_audit_marker(utc_iso(), "FAILED")
            output = {
                "correction_type": correction_type,
                "timestamp": utc_iso(),
                "hard_count_24h": recent_hard,
                **blocked_flags,
                "actions_soft": actions_soft,
                "actions_hard": actions_hard,
                "fix_branch": branch_name,
            }
            print(json.dumps({"result":output}, separators=(",",":")))
            return 7

    # Write correction artifacts
    ts_now = utc_iso()
    hard_count_after = count_recent_hard_corrections()
    summary_payload = {
        "correction_type": correction_type,
        "timestamp": ts_now,
        "hard_count_24h": hard_count_after,
        **blocked_flags,
    }
    atomic_write_json_retry(path("state/mvcrs_last_correction.json"), {
        **summary_payload,
        "actions_soft": actions_soft,
        "actions_hard": actions_hard,
    })
    # Log individual actions
    for act in actions_soft:
        append_jsonl(path("state/mvcrs_correction_log.jsonl"), {"timestamp": act["timestamp"], "name": act["name"], "undo": act["undo"], "action_scope": "soft"})
    for act in actions_hard:
        append_jsonl(path("state/mvcrs_correction_log.jsonl"), {"timestamp": act["timestamp"], "name": act["name"], "undo": act["undo"], "action_scope": "hard"})

    # Merge summary
    merge_summary(summary_payload)
    write_audit_marker(ts_now, "UPDATED")

    output = {
        **summary_payload,
        "actions_soft": actions_soft,
        "actions_hard": actions_hard,
    }
    print(json.dumps({"result":output}, separators=(",",":")))
    return exit_code

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
