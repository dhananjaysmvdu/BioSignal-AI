"""Ethics & Compliance Self-Audit Bridge (Phase XI Instruction 62)."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAIRNESS_CSV = ROOT/"results"/"fairness_aggregates.csv"
TRACE_LOG = ROOT/"notebooks"/"logs"/"traceability.json"
POLICY = ROOT/"config"/"certification_policy.json"
REPORT = ROOT/"results"/"ethics_audit_bridge_report.json"
FED_ERROR = ROOT/"federation"/"federation_error_log.jsonl"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_fairness() -> tuple[float, float]:
    fairness = 100.0
    bias = 0.0
    if FAIRNESS_CSV.exists():
        try:
            with FAIRNESS_CSV.open("r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                vals = [float(row.get("fairness", 100.0)) for row in reader if row.get("fairness")]
                if vals:
                    fairness = sum(vals)/len(vals)
        except Exception:
            pass
    # derive bias from fairness if not explicitly available
    bias = max(0.0, 100.0 - fairness)/100.0
    return fairness, bias


def log_event(event: str, message: str, meta: dict | None = None):
    entry = {"timestamp": utc_iso(), "event": event, "message": message}
    if meta:
        entry["metadata"] = meta
    FED_ERROR.parent.mkdir(parents=True, exist_ok=True)
    with FED_ERROR.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def main():
    fairness, bias = read_fairness()
    policy = {}
    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8")) if POLICY.exists() else {}
    except Exception:
        policy = {}

    should_recalibrate = (fairness < 98.0) or (bias > 0.01)
    action_taken = False
    rc = 0
    if should_recalibrate:
        # Trigger self-healing kernel
        kernel = ROOT/"scripts"/"self_healing"/"self_healing_kernel.py"
        try:
            proc = subprocess.run([sys.executable, str(kernel)], capture_output=True, text=True, timeout=180)
            rc = proc.returncode
            action_taken = (rc == 0)
            log_event("ethics_recalibration", "Triggered self-healing due to ethics thresholds.", {"fairness": fairness, "bias": bias, "returncode": rc})
        except Exception as exc:
            log_event("ethics_recalibration_error", "Failed to run self-healing kernel.", {"error": str(exc)})

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "timestamp": utc_iso(),
        "fairness": fairness,
        "bias": bias,
        "policy": policy,
        "recalibration_triggered": should_recalibrate,
        "action_taken": action_taken,
        "returncode": rc
    }, indent=2), encoding="utf-8")
    print(json.dumps({"recalibration_triggered": should_recalibrate, "action_taken": action_taken}))


if __name__ == "__main__":
    main()
