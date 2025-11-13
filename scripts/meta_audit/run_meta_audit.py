#!/usr/bin/env python3
"""
Meta-Audit: Replication + Drift Detection

- Runs validate_full_reproducibility.py and validate_release_candidate.py in isolated temp directories (cwd only; scripts resolve repo root internally)
- Captures stdout/stderr and exit codes
- Compares with previous entry in meta_audit_log.jsonl to compute simple drift deltas
- Appends a JSON line to meta_audit/meta_audit_log.jsonl
- Writes a detailed report meta_audit/reports/meta_audit_<YYYYMMDD>.json
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
META_DIR = ROOT / "meta_audit"
LOG_PATH = META_DIR / "meta_audit_log.jsonl"
REPORTS_DIR = META_DIR / "reports"

VALIDATORS = [
    ROOT / "scripts" / "workflow_utils" / "validate_full_reproducibility.py",
    ROOT / "scripts" / "workflow_utils" / "validate_release_candidate.py",
]

@dataclass
class RunResult:
    name: str
    exit_code: int
    stdout: str
    stderr: str


def run_in_temp(py_file: Path) -> RunResult:
    name = py_file.stem
    with tempfile.TemporaryDirectory(prefix=f"meta_audit_{name}_") as tmp:
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        # Ensure scripts import behavior isn't affected by cwd; use repo python
        proc = subprocess.run(
            [sys.executable, str(py_file)], cwd=tmp, env=env, capture_output=True, text=True
        )
        return RunResult(
            name=name,
            exit_code=proc.returncode,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
        )


def parse_result_text(text: str) -> dict:
    """Extract a few summary fields when present."""
    summary = {}
    # RESULT line
    m = re.search(r"RESULT:\s*(.+)$", text, flags=re.MULTILINE)
    if m:
        summary["result"] = m.group(1).strip()
    # Capsule tag
    m = re.search(r"Capsule tag\s*\.+\s*([^\s]+)\s*(✅|❌)?", text)
    if m:
        summary["capsule_tag"] = m.group(1)
    # DOI in any line
    m = re.search(r"10\.\d{4,9}/[A-Za-z0-9._;()/:\-]+", text)
    if m:
        summary["doi"] = m.group(0)
    return summary


def read_last_log() -> Optional[dict]:
    if not LOG_PATH.exists():
        return None
    try:
        last = None
        with LOG_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)
        return last
    except Exception:
        return None


def compute_drift(prev: Optional[dict], current: dict) -> dict:
    drift = {"has_prev": bool(prev)}
    if not prev:
        return drift
    # Compare exit codes per tool
    prev_codes = {r["name"]: r["exit_code"] for r in prev.get("runs", [])}
    curr_codes = {r["name"]: r["exit_code"] for r in current.get("runs", [])}
    code_delta = {}
    for k in sorted(set(prev_codes) | set(curr_codes)):
        code_delta[k] = {"prev": prev_codes.get(k), "curr": curr_codes.get(k)}
    drift["exit_code_delta"] = code_delta

    # If available, compare summary.result strings
    prev_results = {r["name"]: r.get("summary", {}).get("result") for r in prev.get("runs", [])}
    curr_results = {r["name"]: r.get("summary", {}).get("result") for r in current.get("runs", [])}
    res_delta = {}
    for k in sorted(set(prev_results) | set(curr_results)):
        if prev_results.get(k) != curr_results.get(k):
            res_delta[k] = {"prev": prev_results.get(k), "curr": curr_results.get(k)}
    if res_delta:
        drift["result_changed"] = res_delta
    return drift


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def main() -> int:
    META_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    runs: list[dict] = []
    for vf in VALIDATORS:
        if not vf.exists():
            runs.append({
                "name": vf.stem,
                "exit_code": 127,
                "stdout": "",
                "stderr": f"validator not found: {vf}",
                "summary": {}
            })
            continue
        rr = run_in_temp(vf)
        runs.append({
            "name": rr.name,
            "exit_code": rr.exit_code,
            "stdout": rr.stdout[-4000:],  # bound size
            "stderr": rr.stderr[-4000:],
            "summary": parse_result_text(rr.stdout),
        })

    entry = {
        "timestamp": iso_now(),
        "runs": runs,
    }

    prev = read_last_log()
    entry["drift"] = compute_drift(prev, entry)

    # Append to JSONL
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Write detailed report for the day
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    report_path = REPORTS_DIR / f"meta_audit_{day}.json"
    report_path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")

    # Exit with non-zero if any validator failed hard (exit!=0)
    hard_fail = any(r["exit_code"] != 0 for r in runs)
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
