"""Dynamic JSON Schema Enforcement Layer (Phase XI Instruction 58).

Auto-discovers *.json and *.jsonl files under selected roots, validates minimal schema
constraints, repairs when possible, and appends schema compliance markers.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [ROOT/"federation", ROOT/"self_healing", ROOT/"portal", ROOT/"integration"]
LOG_PATH = ROOT/"logs"/"schema_auto_repair.jsonl"
AUDIT_PATH = ROOT/"audit_summary.md"
REGISTRY_SCHEMA = ROOT/"templates"/"integrity_registry_schema.json"
AUDIT_SCHEMA = ROOT/"templates"/"audit_schema.json"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_iso8601(s: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+\-]\d{2}:\d{2})$", s))


def append_log(entry: Dict[str, Any]):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def load_json_safe(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # Try to repair simple issues: trailing commas, single quotes
        txt = path.read_text(encoding="utf-8")
        repaired = re.sub(r",\s*([}\]])", r"\\1", txt).replace("'", '"')
        try:
            data = json.loads(repaired)
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            append_log({"timestamp": utc_iso(), "path": str(path.relative_to(ROOT)), "action": "json_repaired"})
            return data
        except Exception:
            # As a last resort, wrap into a minimal object to preserve file
            data = {"timestamp": utc_iso(), "raw": []}
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            append_log({"timestamp": utc_iso(), "path": str(path.relative_to(ROOT)), "action": "json_reencoded"})
            return data


def ensure_keys_types(data: Any, schema: Dict[str, Any]) -> tuple[Any, bool]:
    changed = False
    defaults = schema.get("defaults", {})
    types = schema.get("types", {})
    required = schema.get("required_keys", [])
    if not isinstance(data, dict):
        return data, changed
    # Inject defaults for missing keys
    for k in required:
        if k not in data:
            data[k] = defaults.get(k, None)
            changed = True
    # Type checks
    for k, t in types.items():
        if k in data and data[k] is not None:
            if t == "iso8601":
                if isinstance(data[k], str) and not is_iso8601(data[k]):
                    data[k] = utc_iso()
                    changed = True
            elif t == "string":
                if not isinstance(data[k], str):
                    data[k] = str(data[k])
                    changed = True
            elif t == "number":
                try:
                    data[k] = float(data[k])
                except Exception:
                    data[k] = 0.0
                changed = True
    return data, changed


def validate_and_repair(path: Path, audit_schema: Dict[str, Any]) -> bool:
    repaired = False
    if path.suffix == ".jsonl":
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        new_lines = []
        for line in lines:
            try:
                obj = json.loads(line)
            except Exception:
                obj = {"timestamp": utc_iso(), "message": "line_reencoded"}
                repaired = True
            obj, ch = ensure_keys_types(obj, audit_schema)
            repaired = repaired or ch
            new_lines.append(json.dumps(obj))
        path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
        if repaired:
            append_log({"timestamp": utc_iso(), "path": str(path.relative_to(ROOT)), "action": "jsonl_repaired"})
        return repaired
    else:
        data = load_json_safe(path)
        data, ch = ensure_keys_types(data, audit_schema)
        repaired = repaired or ch
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if repaired:
            append_log({"timestamp": utc_iso(), "path": str(path.relative_to(ROOT)), "action": "json_repaired_keys"})
        return repaired


def main():
    audit_schema = json.loads(AUDIT_SCHEMA.read_text(encoding="utf-8")) if AUDIT_SCHEMA.exists() else {"required_keys": ["timestamp"], "types": {"timestamp": "iso8601"}}
    repaired_any = False
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for p in base.rglob("*.json"):
            repaired_any |= validate_and_repair(p, audit_schema)
        for p in base.rglob("*.jsonl"):
            repaired_any |= validate_and_repair(p, audit_schema)

    # Append audit marker
    if AUDIT_PATH.exists():
        marker = f"<!-- SCHEMA_ENFORCEMENT: UPDATED {utc_iso()} -->\n"
        with AUDIT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(marker)

    print(json.dumps({"repaired": repaired_any}))


if __name__ == "__main__":
    main()
