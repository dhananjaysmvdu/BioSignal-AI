#!/usr/bin/env python3
"""
Validate Integrity Metrics Registry schema and append schema hash footer.

Checks that exports/integrity_metrics_registry.csv header matches the
canonical schema. On mismatch, prints a diff, updates audit summary marker,
and exits with code 1. Always ensures a trailing schema hash footer exists.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import List, Tuple


CANONICAL_FIELDS: List[str] = [
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


def compute_schema_hash(fields: List[str] = None) -> str:
    f = fields or CANONICAL_FIELDS
    s = ",".join(f).encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def read_first_header_line(csv_path: Path) -> str:
    if not csv_path.exists():
        return ""
    for line in csv_path.read_text(encoding="utf-8").splitlines():
        ls = line.strip()
        if not ls:
            continue
        if ls.startswith("#"):
            continue
        return ls
    return ""


def ensure_footer_hash(csv_path: Path, schema_hash: str) -> bool:
    """Ensure the CSV ends with a comment line containing the schema hash.
    Returns True if file was modified.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    content = csv_path.read_text(encoding="utf-8") if csv_path.exists() else ""
    lines = content.splitlines()
    # Remove existing schema hash lines anywhere
    lines = [ln for ln in lines if not ln.strip().startswith("# schema_hash:")]
    footer = f"# schema_hash: {schema_hash}"
    if lines and lines[-1].strip() != footer:
        lines.append(footer)
    elif not lines:
        # no content, create header and footer? do not invent header here; only write footer
        lines = [footer]
    new_content = "\n".join(lines) + "\n"
    if new_content != content:
        csv_path.write_text(new_content, encoding="utf-8")
        return True
    return False


def update_audit_marker(audit_path: Path, message: str) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    if not audit_path.exists():
        audit_path.write_text("# Audit Summary\n\n", encoding="utf-8")
    content = audit_path.read_text(encoding="utf-8")
    begin = "<!-- INTEGRITY_REGISTRY_SCHEMA:BEGIN -->"
    end = "<!-- INTEGRITY_REGISTRY_SCHEMA:END -->"
    section = f"{begin}\n{message}\n{end}"
    import re
    if begin in content and end in content:
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
        content = pattern.sub(section, content)
    else:
        content = content.rstrip() + "\n\n" + section + "\n"
    audit_path.write_text(content, encoding="utf-8")


def compare_headers(actual: List[str], expected: List[str]) -> Tuple[bool, str]:
    ok = actual == expected
    if ok:
        return True, ""
    # Build a small diff summary
    actual_set = set(actual)
    expected_set = set(expected)
    missing = sorted(list(expected_set - actual_set))
    extra = sorted(list(actual_set - expected_set))
    msg_lines = [
        "Integrity registry schema mismatch:",
        f"Expected: {','.join(expected)}",
        f"Actual:   {','.join(actual)}",
    ]
    if missing:
        msg_lines.append(f"Missing columns: {', '.join(missing)}")
    if extra:
        msg_lines.append(f"Extra columns: {', '.join(extra)}")
    return False, "\n".join(msg_lines)


def validate(registry: Path, audit_summary: Path) -> int:
    expected = CANONICAL_FIELDS
    schema_hash = compute_schema_hash(expected)

    header_line = read_first_header_line(registry)
    if not header_line:
        # Still append footer hash for reproducibility
        ensure_footer_hash(registry, schema_hash)
        msg = "Integrity registry missing or empty; schema cannot be validated."
        print(msg)
        update_audit_marker(audit_summary, f"⚠️ {msg}")
        return 1

    actual = [c.strip() for c in header_line.split(",")]
    ok, diff_msg = compare_headers(actual, expected)

    # Always ensure footer hash regardless of pass/fail
    changed = ensure_footer_hash(registry, schema_hash)

    if ok:
        msg = f"Integrity registry schema OK (hash {schema_hash[:12]})."
        print(msg)
        update_audit_marker(audit_summary, f"✅ {msg}")
        return 0
    else:
        print(diff_msg)
        update_audit_marker(audit_summary, f"❌ {diff_msg}")
        return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate integrity registry schema")
    p.add_argument("--registry", type=Path, default=Path("exports/integrity_metrics_registry.csv"))
    p.add_argument("--audit-summary", type=Path, default=Path("reports/audit_summary.md"))
    args = p.parse_args(argv)
    return validate(args.registry, args.audit_summary)


if __name__ == "__main__":
    sys.exit(main())
