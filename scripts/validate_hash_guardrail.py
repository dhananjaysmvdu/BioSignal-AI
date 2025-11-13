"""Guardrail Consistency Validator (Phase X Instruction 52)

Verifies canonical schema header fields, recomputes SHA-256 for integrity registry,
compares against federation_status.json recorded hash, and ensures guardrail marker
present in audit summaries. Auto-repairs header order if mismatch detected. Logs result
to guardrail_validation_log.jsonl.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "templates" / "integrity_registry_schema.json"
REGISTRY = ROOT / "exports" / "integrity_metrics_registry.csv"
FED_STATUS = ROOT / "federation" / "federation_status.json"
GUARD_LOG = ROOT / "federation" / "guardrail_validation_log.jsonl"
AUDIT_ROOT = ROOT / "audit_summary.md"
AUDIT_REPORT = ROOT / "reports" / "audit_summary.md"

CANONICAL_FIELDS = ["timestamp", "metric", "value", "integrity_score", "notes"]


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def recompute_registry_hash() -> str:
    if not REGISTRY.exists():
        return ""
    h = hashlib.sha256()
    h.update(REGISTRY.read_bytes())
    return h.hexdigest()


def repair_header_order() -> bool:
    if not REGISTRY.exists():
        return False
    lines = REGISTRY.read_text(encoding="utf-8").splitlines()
    if not lines:
        return False
    current_header = lines[0].split(",")
    if current_header == CANONICAL_FIELDS:
        return False
    # Reorder header if fields are a permutation
    if sorted(current_header) == sorted(CANONICAL_FIELDS):
        lines[0] = ",".join(CANONICAL_FIELDS)
        REGISTRY.write_text("\n".join(lines), encoding="utf-8")
        return True
    return False


def guardrail_marker_present(text: str) -> bool:
    return "HASH_GUARDRAIL" in text or "hash guardrail" in text.lower()


def append_log(entry: dict):
    GUARD_LOG.parent.mkdir(parents=True, exist_ok=True)
    with GUARD_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def main():
    fed_status = load_json(FED_STATUS)
    recorded_hash = ""
    # Attempt to locate hash in federation status
    if "hash_results" in fed_status:
        hr = fed_status["hash_results"]
        if isinstance(hr, dict):
            recorded_hash = next(iter(hr.values()), "")
        elif isinstance(hr, list) and hr:
            recorded_hash = str(hr[-1])

    repaired = repair_header_order()
    recomputed = recompute_registry_hash()
    hash_match = bool(recomputed) and (recomputed in recorded_hash)

    audit_root_txt = AUDIT_ROOT.read_text(encoding="utf-8") if AUDIT_ROOT.exists() else ""
    audit_report_txt = AUDIT_REPORT.read_text(encoding="utf-8") if AUDIT_REPORT.exists() else ""
    guardrail_markers_ok = guardrail_marker_present(audit_root_txt) and guardrail_marker_present(audit_report_txt)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recorded_hash_fragment": recorded_hash[:16],
        "recomputed_hash": recomputed,
        "hash_match": hash_match,
        "header_repaired": repaired,
        "guardrail_markers_ok": guardrail_markers_ok,
    }
    append_log(entry)
    print(json.dumps(entry))

    if not hash_match or not guardrail_markers_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
