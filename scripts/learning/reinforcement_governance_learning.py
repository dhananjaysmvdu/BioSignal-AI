#!/usr/bin/env python3
import argparse
import io
import json
import os
import sys
import time
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

# Paths
ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state"
FORENSICS_DIR = ROOT / "forensics" / "forecast"
FEDERATION_DIR = ROOT / "federation"
AUDIT_FILE = ROOT / "audit_summary.md"

THRESHOLD_POLICY = STATE_DIR / "threshold_policy.json"
POLICY_FUSION_STATE = STATE_DIR / "policy_fusion_state.json"
ADAPTIVE_RESPONSE_HISTORY = STATE_DIR / "adaptive_response_history.jsonl"
FORECAST_FILE = FORENSICS_DIR / "forensic_forecast.json"
PROVENANCE_CONSENSUS = FEDERATION_DIR / "provenance_consensus.json"
REPUTATION_INDEX = FEDERATION_DIR / "reputation_index.json"

RDGL_POLICY = STATE_DIR / "rdgl_policy_adjustments.json"
RDGL_REWARD_LOG = STATE_DIR / "rdgl_reward_log.jsonl"

LEARNING_RATE = 0.05

# Import metrics helper
sys.path.insert(0, str((ROOT / "scripts" / "learning").resolve()))
from rdgl_metrics import compute_daily_reward, compute_confidence_state, summarize_learning_window  # type: ignore


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, data: Dict[str, Any], retries: List[int] = [1, 3, 9]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    last_err = None
    for delay in [0] + retries:
        try:
            if delay:
                time.sleep(delay)
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise last_err  # type: ignore[misc]


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def create_fix_branch(prefix: str, reason: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch = f"fix/{prefix}-{ts}"
    try:
        subprocess.run(["git", "checkout", "-b", branch], check=False)
        append_audit_marker(f"RDGL: CI_FAIL {utcnow_iso()} :: {reason}")
    except Exception:
        pass


def append_audit_marker(marker: str = None) -> None:  # type: ignore[assignment]
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    text = AUDIT_FILE.read_text(encoding="utf-8") if AUDIT_FILE.exists() else ""
    if marker is None:
        marker = f"RDGL: UPDATED {utcnow_iso()}"
    html_marker = f"<!-- {marker} -->"
    # Idempotent: if an RDGL UPDATED marker already exists, skip adding another
    if "RDGL: UPDATED" in text:
        return
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write("\n" + html_marker + "\n")


def _risk_improvement(prev: str, curr: str) -> bool:
    order = {"low": 0, "medium": 1, "high": 2}
    return order.get(curr, 1) < order.get(prev, 1)


def derive_features_24h() -> Dict[str, Any]:
    # Inputs
    threshold = read_json(THRESHOLD_POLICY, {}) or {}
    fusion = read_json(POLICY_FUSION_STATE, {}) or {}
    forecast = read_json(FORECAST_FILE, {}) or {}
    consensus = read_json(PROVENANCE_CONSENSUS, {}) or {}
    reputation = read_json(REPUTATION_INDEX, {}) or {}
    responses: List[Dict[str, Any]] = read_jsonl(ADAPTIVE_RESPONSE_HISTORY)
    reward_log = read_jsonl(RDGL_REWARD_LOG)

    # Forecast accuracy improvement heuristic: last forecast risk vs current
    prev_risk = None
    for rec in reversed(reward_log):
        if rec.get("forecast_risk"):
            prev_risk = rec["forecast_risk"]
            break
    curr_risk = (forecast.get("forecast_risk") or forecast.get("risk_level") or "medium").lower()
    forecast_accuracy_improvement = False
    if prev_risk:
        forecast_accuracy_improvement = _risk_improvement(prev_risk, curr_risk)

    # Reduced high-risk days heuristic: previous risk == high → current not high
    reduced_high_risk_days = prev_risk == "high" and curr_risk != "high"

    # Self-healing events in last 24h
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    def _ts(s: str) -> datetime:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return now
    self_heals = sum(1 for r in responses if _ts(str(r.get("timestamp", utcnow_iso()))) >= day_ago and "self" in str(r.get("action", "")).lower())

    # Avoided RED: current fusion not RED
    fusion_level = (fusion.get("fusion_level") or fusion.get("level") or "FUSION_YELLOW").upper()
    avoided_red = fusion_level != "FUSION_RED"

    # Unnecessary actions: responses in last 24h when fusion GREEN and forecast low
    fusion_green = fusion_level == "FUSION_GREEN"
    low_forecast = curr_risk == "low"
    unnecessary_actions = sum(1 for r in responses if _ts(str(r.get("timestamp", utcnow_iso()))) >= day_ago and fusion_green and low_forecast)

    # Safety brake engagements (read from fusion inputs)
    safety_brake_engagements = 1 if (fusion.get("inputs", {}).get("safety_brake_engaged") is True) else 0

    # Manual unlocks: response flagged, or trust lock flip to false
    manual_unlocks = sum(1 for r in responses if _ts(str(r.get("timestamp", utcnow_iso()))) >= day_ago and (r.get("manual_unlock") is True or "manual_unlock" in str(r).lower()))

    return {
        "forecast_accuracy_improvement": forecast_accuracy_improvement,
        "reduced_high_risk_days": bool(reduced_high_risk_days),
        "self_heals": int(self_heals),
        "avoided_red": bool(avoided_red),
        "unnecessary_actions": int(unnecessary_actions),
        "safety_brake_engagements": int(safety_brake_engagements),
        "manual_unlocks": int(manual_unlocks),
        "current": {
            "forecast_risk": curr_risk,
            "fusion_level": fusion_level,
        },
    }


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def run_rdgl(dry_run: bool = False) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Load last score
    last_policy = read_json(RDGL_POLICY, {}) or {}
    old_score = float(last_policy.get("policy_score", 50.0))

    # Derive features + compute reward
    features = derive_features_24h()
    reward, breakdown = compute_daily_reward(features)

    # Update score
    new_score = clamp(old_score + reward * LEARNING_RATE, 0.0, 100.0)

    # Determine behavior mode and shifts
    if new_score > 70:
        mode = "Relaxed"
        shift_range = [2, 3]
    elif 40 <= new_score <= 70:
        mode = "Normal"
        shift_range = [1, 2]
    elif new_score < 20:
        mode = "Locked"
        shift_range = [0, 0]
    else:
        mode = "Tightening"
        shift_range = [3, 5]

    # Prepare outputs
    now_iso = utcnow_iso()
    policy_out: Dict[str, Any] = {
        "policy_score": round(new_score, 2),
        "previous_score": round(old_score, 2),
        "reward_24h": round(reward, 3),
        "mode": mode,
        "shift_percent_range": shift_range,
        "last_updated": now_iso,
        "trend": None,
    }

    # Summarize recent trend
    reward_log = read_jsonl(RDGL_REWARD_LOG)
    preview = reward_log + [{
        "timestamp": now_iso,
        "reward": reward,
        "policy_score": policy_out["policy_score"],
    }]
    summary = summarize_learning_window(preview, days=7)
    policy_out["trend"] = summary.get("trend", "Stable")

    # Append reward record
    reward_rec = {
        "timestamp": now_iso,
        "reward": reward,
        "breakdown": breakdown,
        "policy_score": policy_out["policy_score"],
        "forecast_risk": features["current"]["forecast_risk"],
        "fusion_level": features["current"]["fusion_level"],
        "learning_rate": LEARNING_RATE,
    }

    # Idempotent audit marker on success
    try:
        if not dry_run:
            atomic_write_json(RDGL_POLICY, policy_out)
            append_jsonl(RDGL_REWARD_LOG, reward_rec)
            append_audit_marker()
        else:
            policy_out["dry_run"] = True
            print(json.dumps(policy_out, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:  # noqa: BLE001
        create_fix_branch("rdgl", f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reinforcement-Driven Governance Learning (RDGL)")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing outputs")
    args = parser.parse_args()
    sys.exit(run_rdgl(dry_run=args.dry_run))
