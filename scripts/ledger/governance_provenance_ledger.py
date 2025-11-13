"""Governance Provenance Ledger builder (Phase XIII Instruction 71).

Aggregates Phase I–XII completion reports into a public JSONL ledger with
cryptographic hash anchoring for reproducibility.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "governance_provenance_ledger.jsonl"
HASH_OUT = ROOT / "governance_ledger_hash.json"
AUDIT_MD = ROOT / "audit_summary.md"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_commit_hash() -> str:
    # Prefer environment CI variables, fallback to local git
    for key in ("GITHUB_SHA", "CI_COMMIT_SHA"):
        val = os.environ.get(key)
        if val:
            return val[:40]
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT))
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def list_phase_reports() -> List[Path]:
    pats = sorted(ROOT.glob("PHASE_*_COMPLETION_REPORT.md"))
    return [p for p in pats if p.is_file()]


def extract_field(text: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def infer_integrity_score(text: str) -> float:
    # try FII percentage first
    m = re.search(r"FII\D+(\d{1,3}(?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        try:
            val = float(m.group(1))
            return max(0.0, min(100.0, val))
        except Exception:
            pass
    # else if PASSED, return 100
    if re.search(r"(tests|validation)\s*:\s*passed", text, re.IGNORECASE):
        return 100.0
    return 0.0


def load_existing() -> list[dict]:
    if not LEDGER.exists():
        return []
    records: list[dict] = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records


def upsert(records: list[dict], entry: dict) -> list[dict]:
    key = (entry.get("phase_id"), entry.get("version_tag"))
    replaced = False
    new: list[dict] = []
    for r in records:
        k = (r.get("phase_id"), r.get("version_tag"))
        if k == key:
            new.append(entry)
            replaced = True
        else:
            new.append(r)
    if not replaced:
        new.append(entry)
    return new


def write_ledger(entries: list[dict]) -> None:
    lines = [json.dumps(e, ensure_ascii=False) for e in entries]
    LEDGER.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def write_hash_summary() -> dict:
    digest = sha256_path(LEDGER) if LEDGER.exists() else None
    payload = {"timestamp": utc_iso(), "sha256": digest, "entries": sum(1 for _ in LEDGER.open()) if LEDGER.exists() else 0}
    HASH_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def append_audit_marker() -> None:
    if not AUDIT_MD.exists():
        return
    with AUDIT_MD.open("a", encoding="utf-8") as fh:
        fh.write(f"<!-- GOVERNANCE_PROVENANCE_LEDGER: UPDATED {utc_iso()} -->\n")


def main() -> int:
    existing = load_existing()
    reports = list_phase_reports()
    for p in reports:
        text = p.read_text(encoding="utf-8")
        phase_id = p.stem.replace("PHASE_", "").replace("_COMPLETION_REPORT", "")
        version_tag = extract_field(text, r"^Tag:\s*([^\n\(]+)\s*(?:\(.*?\))?\s*$") or "unknown"
        status = extract_field(text, r"Status\s*:\s*([^\n]+)") or extract_field(text, r"Certification\s*:\s*([^\n]+)") or "unknown"
        entry = {
            "phase_id": phase_id,
            "version_tag": version_tag.strip(),
            "timestamp": utc_iso(),
            "commit_hash": git_commit_hash(),
            "integrity_score": infer_integrity_score(text),
            "certification": status.strip(),
        }
        existing = upsert(existing, entry)

    # Sort by phase order if numeric, else by name
    def sort_key(e: dict):
        try:
            return int(re.sub(r"\D", "", e.get("phase_id", "")))
        except Exception:
            return 9999
    existing = sorted(existing, key=sort_key)
    write_ledger(existing)
    write_hash_summary()
    append_audit_marker()
    print(json.dumps({"status": "ok", "entries": len(existing)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
