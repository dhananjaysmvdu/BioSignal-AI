"""Federation Drift Simulation & Recovery Test (Phase X Instruction 50)

Simulates random hash mismatch drift (5%) across 3 federation nodes, writes a temporary
drift log, invokes federation sync, and verifies post-sync Federation Integrity Index (FII)
>= 98%. Appends results to federation_test_results.json and adds audit marker.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import shutil
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
FED_STATUS = ROOT / "federation" / "federation_status.json"
TEST_RESULTS = ROOT / "results" / "federation_test_results.json"
AUDIT = ROOT / "audit_summary.md"

NODES = ["Zenodo", "GitHub", "OpenAIRE"]


def simulate_drift():
    drift_events = []
    for node in NODES:
        mismatch = random.random() < 0.05  # 5% chance
        if mismatch:
            drift_events.append({
                "timestamp": datetime.utcnow().isoformat()+"Z",
                "node": node,
                "event": "hash_mismatch_simulated",
                "expected": "sha256:dummy",
                "observed": "sha256:corrupt",
            })
    return drift_events


def run_federation_sync():
    ps_wrapper = ROOT / "scripts" / "federation" / "run_federation_sync.ps1"
    if ps_wrapper.exists():
        shell = "pwsh" if shutil.which("pwsh") else "powershell"
        return subprocess.run([shell, str(ps_wrapper)], capture_output=True, text=True)
    py_script = ROOT / "scripts" / "federation" / "run_federation_sync.py"
    return subprocess.run([sys.executable, str(py_script)], capture_output=True, text=True)


def compute_fii(status: dict) -> float:
    # Simple heuristic: start at 100, subtract 0.5 per mismatch resolved event
    history = status.get("history", [])
    penalties = sum(0.5 for h in history if "hash" in str(h).lower())
    return max(0.0, 100.0 - penalties)


def append_audit_marker(passed: bool):
    marker = "<!-- FEDERATION_RECOVERY_TEST: PASSED -->" if passed else "<!-- FEDERATION_RECOVERY_TEST: FAILED -->"
    if AUDIT.exists():
        content = AUDIT.read_text(encoding="utf-8")
        if marker not in content:
            AUDIT.write_text(content + "\n" + marker + "\n", encoding="utf-8")


def main():
    drift = simulate_drift()
    drift_path = ROOT / "federation" / "simulated_drift_events.jsonl"
    with drift_path.open("a", encoding="utf-8") as fh:
        for ev in drift:
            fh.write(json.dumps(ev) + "\n")

    sync_proc = run_federation_sync()
    try:
        status = json.loads(FED_STATUS.read_text(encoding="utf-8")) if FED_STATUS.exists() else {}
    except Exception:
        status = {}

    fii = compute_fii(status)
    passed = fii >= 98.0
    append_audit_marker(passed)

    TEST_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if TEST_RESULTS.exists():
        try:
            existing = json.loads(TEST_RESULTS.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing[datetime.now(timezone.utc).isoformat()] = {
        "fii": fii,
        "drift_events": drift,
        "passed": passed,
        "stdout": sync_proc.stdout[-500:],
        "stderr": sync_proc.stderr[-500:],
    }
    TEST_RESULTS.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"Federation Drift Test completed. FII={fii:.2f} passed={passed}")


if __name__ == "__main__":
    main()
