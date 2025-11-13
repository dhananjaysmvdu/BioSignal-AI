#!/usr/bin/env python3
"""
Schema Provenance Ledger

Maintains an append-only JSONL ledger capturing the canonical integrity
registry schema (fields and SHA-256) and the commit in which it was observed.

Behavior:
- Reads canonical fields and hash from validate_integrity_registry_schema.py
- Appends to exports/schema_provenance_ledger.jsonl if the hash changed
- Updates SCHEMA_PROVENANCE marker in reports/audit_summary.md
- Always exits 0 (CI-safe)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_canonical() -> tuple[List[str], str]:
    try:
        from scripts.workflow_utils.validate_integrity_registry_schema import (
            CANONICAL_FIELDS,
            compute_schema_hash,
        )
        fields = list(CANONICAL_FIELDS)
        return fields, compute_schema_hash(fields)
    except Exception:
        # Fallback (should match validator)
        fields = [
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
        import hashlib

        return fields, hashlib.sha256(
            ",".join(fields).encode("utf-8")
        ).hexdigest()


def current_commit_short() -> str:
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha[:7]
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL)
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def read_last_entry(ledger: Path) -> Optional[Dict[str, Any]]:
    if not ledger.exists():
        return None
    try:
        with ledger.open("r", encoding="utf-8") as f:
            last = None
            for line in f:
                line = line.strip()
                if not line:
                    continue
                last = json.loads(line)
        return last
    except Exception:
        return None


def append_entry(ledger: Path, entry: Dict[str, Any]) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def update_audit_marker(audit_path: Path, message: str) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    if not audit_path.exists():
        audit_path.write_text("# Audit Summary\n\n", encoding="utf-8")
    content = audit_path.read_text(encoding="utf-8")
    begin = "<!-- SCHEMA_PROVENANCE:BEGIN -->"
    end = "<!-- SCHEMA_PROVENANCE:END -->"
    section = f"{begin}\n{message}\n{end}"
    import re
    if begin in content and end in content:
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
        content = pattern.sub(section, content)
    else:
        content = content.rstrip() + "\n\n" + section + "\n"
    audit_path.write_text(content, encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Maintain schema provenance ledger")
    p.add_argument("--ledger", type=Path, default=Path("exports/schema_provenance_ledger.jsonl"))
    p.add_argument("--audit-summary", type=Path, default=Path("reports/audit_summary.md"))
    args = p.parse_args(argv)

    try:
        fields, schema_hash = load_canonical()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        commit = current_commit_short()

        last = read_last_entry(args.ledger)
        if last and last.get("schema_hash") == schema_hash:
            msg = f"Schema ledger verified — last entry {schema_hash[:12]}… (no change detected)"
            print(msg)
            update_audit_marker(args.audit_summary, msg)
            return 0

        entry = {
            "timestamp": now,
            "schema_hash": schema_hash,
            "fields": fields,
            "commit": commit,
        }
        append_entry(args.ledger, entry)
        msg = f"Schema ledger updated — new entry {schema_hash[:12]}…"
        print(msg)
        update_audit_marker(args.audit_summary, msg)
        return 0
    except Exception as e:
        print(f"Schema ledger error: {e}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
