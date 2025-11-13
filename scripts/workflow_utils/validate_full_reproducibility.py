#!/usr/bin/env python3
"""
Meta-validation: End-to-End Reproducibility Validation

Checks in one sweep:
- Latest capsule tag exists locally and is pushed to origin
- Integrity and Reproducibility badge JSONs have non-null values and matching timestamps
- README.md and GOVERNANCE_TRANSPARENCY.md agree on DOI and capsule tag
- Integrity registry header matches canonical schema

Behavior:
- Prints a one-page summary
- Non-blocking for most issues (exit code 0), but exits 1 if capsule tag is missing locally or not pushed
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
BADGES_DIR = ROOT / "badges"
EXPORTS_DIR = ROOT / "exports"
README = ROOT / "README.md"
MANIFEST = ROOT / "GOVERNANCE_TRANSPARENCY.md"

INTEGRITY_BADGE = BADGES_DIR / "integrity_status.json"
REPRO_BADGE = BADGES_DIR / "reproducibility_status.json"
REGISTRY = EXPORTS_DIR / "integrity_metrics_registry.csv"

# Canonical schema (kept in sync with generate_transparency_manifest.py)
CANONICAL_SCHEMA = [
    "timestamp",
    "integrity_score",
    "violations",
    "warnings",
    "health_score",
    "rri",
    "mpi",
    "confidence",
    "status",
]


@dataclass
class CheckResult:
    ok: bool
    message: str


def _run_git(args: list[str]) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git not found"


def latest_capsule_tag() -> Optional[str]:
    # Prefer creation date sort, fallback to lexical if not supported
    code, out, _ = _run_git(["for-each-ref", "--sort=-creatordate", "--format=%(refname:short)", "refs/tags/capsule-*"])
    if code == 0 and out:
        return out.splitlines()[0]
    code, out, _ = _run_git(["tag", "--list", "capsule-*"])
    if code == 0 and out:
        # lexical sort descending (YYYY-MM-DD sorts correctly)
        return sorted(out.splitlines(), reverse=True)[0]
    return None


def tag_pushed(tag: str) -> bool:
    code, out, _ = _run_git(["ls-remote", "--tags", "origin", f"refs/tags/{tag}"])
    if code != 0:
        return False
    return bool(out.strip())


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _badge_value_and_ts(path: Path) -> Tuple[Optional[str], Optional[datetime]]:
    data = _read_json(path) or {}
    message = data.get("message")
    # normalize message: treat missing or "n/a" as None
    if isinstance(message, str) and message.strip().lower() == "n/a":
        message = None
    if not isinstance(message, str):
        message = None

    # timestamp keys we recognize
    ts_raw = None
    for key in ("timestamp", "updated_at", "updatedAt", "updated"):
        if key in data:
            ts_raw = data.get(key)
            break
    ts_val: Optional[datetime] = None
    if isinstance(ts_raw, str):
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                if fmt.endswith("%z"):
                    ts_val = datetime.strptime(ts_raw, fmt)
                else:
                    ts_val = datetime.strptime(ts_raw, fmt).replace(tzinfo=timezone.utc)
                break
            except Exception:
                continue
    if ts_val is None and path.exists():
        # Fallback: file mtime (UTC)
        ts_val = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return message, ts_val


def _extract_first(pattern: re.Pattern[str], text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(0) if m else None


def read_files_for_linkage() -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    doi_re = re.compile(r"10\.\d{4,9}/[A-Za-z0-9._;()/:\-]+")
    tag_re = re.compile(r"capsule-\d{4}-\d{2}-\d{2}")

    readme_text = README.read_text(encoding="utf-8", errors="ignore") if README.exists() else ""
    manifest_text = MANIFEST.read_text(encoding="utf-8", errors="ignore") if MANIFEST.exists() else ""

    doi_r = _extract_first(doi_re, readme_text)
    doi_m = _extract_first(doi_re, manifest_text)
    tag_r = _extract_first(tag_re, readme_text)
    tag_m = _extract_first(tag_re, manifest_text)
    return doi_r, doi_m, tag_r, tag_m


def check_registry_schema() -> CheckResult:
    if not REGISTRY.exists():
        return CheckResult(False, "integrity_metrics_registry.csv missing")
    try:
        header = (REGISTRY.read_text(encoding="utf-8").splitlines() or [""])[0]
        fields = [c.strip() for c in header.split(",")]
        ok = fields == CANONICAL_SCHEMA
        return CheckResult(ok, "Header matches canonical schema" if ok else f"Header mismatch: {fields}")
    except Exception as e:
        return CheckResult(False, f"Error reading registry: {e}")


def fmt_pct_or_na(msg: Optional[str]) -> Tuple[str, bool]:
    if msg is None:
        return "n/a", False
    return msg, True


def _fmt_check_line(label: str, value: str, ok: bool) -> str:
    mark = "✅" if ok else "❌"
    dots = "." * max(1, 25 - len(label))
    return f"{label} {dots} {value} {mark}"


def main() -> int:
    # 1) Capsule tag
    tag = latest_capsule_tag()
    tag_ok = bool(tag)
    pushed_ok = False
    if tag:
        pushed_ok = tag_pushed(tag)

    # 2) Badges
    integ_val, integ_ts = _badge_value_and_ts(INTEGRITY_BADGE)
    repro_val, repro_ts = _badge_value_and_ts(REPRO_BADGE)
    integ_msg, integ_ok = fmt_pct_or_na(integ_val)
    repro_msg, repro_ok = fmt_pct_or_na(repro_val)
    # timestamps considered matching if both exist and within 5 minutes
    ts_match = False
    if integ_ts and repro_ts:
        delta = abs((integ_ts - repro_ts).total_seconds())
        ts_match = delta <= 300

    # 3) Linkage in README & Manifest
    doi_r, doi_m, tag_r, tag_m = read_files_for_linkage()
    doi_ok = bool(doi_r) and bool(doi_m) and (doi_r == doi_m)
    # Capsule tag in docs should match latest tag if present
    tag_docs_ok = bool(tag_r) and bool(tag_m) and (tag_r == tag_m)
    tag_consistent_with_latest = tag_ok and tag_docs_ok and (tag_r == tag)
    manifest_linkage_ok = doi_ok and tag_docs_ok

    # 4) Registry schema
    schema_res = check_registry_schema()

    # Render summary
    print("REPRODUCIBILITY VALIDATION")
    print("--------------------------")
    print(_fmt_check_line("📦 Capsule tag", tag or "missing", tag_ok))
    print(_fmt_check_line("⇡ Pushed to origin", tag if pushed_ok else "not pushed", pushed_ok))
    print(_fmt_check_line("🏷️ DOI", doi_r or "missing", doi_ok))
    print(_fmt_check_line("🛡️ Integrity badge", integ_msg, integ_ok))
    print(_fmt_check_line("🔁 Reproducibility badge", repro_msg, repro_ok))
    print(_fmt_check_line("⏱️ Badge timestamps match", "yes" if ts_match else "no", ts_match))
    print(_fmt_check_line("🧾 Manifest linkage", "Verified" if manifest_linkage_ok else "Mismatch", manifest_linkage_ok))
    print(_fmt_check_line("📊 Registry schema", "OK" if schema_res.ok else "Invalid", schema_res.ok))

    all_ok = tag_ok and pushed_ok and integ_ok and repro_ok and ts_match and manifest_linkage_ok and schema_res.ok and tag_consistent_with_latest
    if all_ok:
        print("RESULT: FULLY REPRODUCIBLE ✔")
    else:
        print("RESULT: NEEDS ATTENTION ✖")

    # Exit policy: only fail on missing/unpushed capsule tag to gate pre-release
    exit_code = 0
    if not tag_ok or not pushed_ok:
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
