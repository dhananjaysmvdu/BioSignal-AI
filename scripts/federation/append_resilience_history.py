"""Append resilience metrics to federation_resilience_history.csv (Phase X Instruction 53).

Metrics appended: timestamp (UTC), FII, recovery_success_rate, retry_rate.
This script reads federation_status.json, self_healing_status.json and workflow_failures.jsonl.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
FED_STATUS = ROOT / "federation" / "federation_status.json"
HEAL_STATUS = ROOT / "self_healing" / "self_healing_status.json"
WORKFLOW_FAIL = ROOT / "logs" / "workflow_failures.jsonl"
HISTORY = ROOT / "results" / "federation_resilience_history.csv"


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_last_retry(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        *_, last = path.read_text(encoding="utf-8").strip().splitlines()
        data = json.loads(last)
        return int(data.get("attempt", 0))
    except Exception:
        return 0


def compute_fii(status: dict) -> float:
    history = status.get("history", [])
    penalties = sum(0.5 for h in history if "hash" in str(h).lower())
    return max(0.0, 100.0 - penalties)


def recovery_success_rate(heal_status: dict) -> float:
    events = heal_status.get("events", [])
    if not events:
        return 100.0
    successes = sum(1 for e in events if "restored" in json.dumps(e).lower())
    return (successes / max(len(events), 1)) * 100.0


def main():
    fed = load_json(FED_STATUS)
    heal = load_json(HEAL_STATUS)
    fii = compute_fii(fed)
    recovery_rate = recovery_success_rate(heal)
    last_retry = read_last_retry(WORKFLOW_FAIL)
    retry_rate = (last_retry / 3.0) * 100.0  # relative to max attempts

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not HISTORY.exists()
    with HISTORY.open("a", encoding="utf-8") as fh:
        if header_needed:
            fh.write("timestamp_utc,fii,recovery_success_rate,retry_rate\n")
        fh.write(f"{datetime.now(timezone.utc).isoformat()},{fii:.2f},{recovery_rate:.2f},{retry_rate:.2f}\n")
    print(f"Appended resilience metrics: FII={fii:.2f} recovery={recovery_rate:.2f}% retry_rate={retry_rate:.2f}%")


if __name__ == "__main__":
    main()
