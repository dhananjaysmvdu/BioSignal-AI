#!/usr/bin/env python3
"""
Generate Integrity Metrics Registry

Consolidates reflex integrity sentinel outputs with key reflex governance metrics
into a longitudinal CSV dataset for external analytics and compliance tracking.

Reads:
  reports/reflex_integrity.json
  reports/reflex_self_audit.json
  reports/reflex_reinforcement.json
  reports/reflex_health_dashboard.html (optional; used to infer cycle count)

Outputs:
  exports/integrity_metrics_registry.csv
    Columns: timestamp, integrity_score, violations, warnings, health_score, rri, mpi, confidence, status

  Updates audit summary with INTEGRITY_REGISTRY marker:
  <!-- INTEGRITY_REGISTRY:BEGIN -->
  📘 Integrity registry updated — N total entries tracked (latest score: X%).
  <!-- INTEGRITY_REGISTRY:END -->

Behavior: Always exits 0.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

REGISTRY_HEADER = [
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

def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def parse_cycle_count(dashboard_html: Path) -> Optional[int]:
    if not dashboard_html.exists():
        return None
    try:
        html = dashboard_html.read_text(encoding="utf-8")
        # Look for header "Health Score Timeline (Last X Cycles)"
        m = re.search(r"Health Score Timeline \(Last (\d+) Cycles\)", html)
        if m:
            return int(m.group(1))
        # Fallback: count data points from 'healthScores' JSON array if present
        m2 = re.search(r"healthScores = (\[[^\]]*\])", html)
        if m2:
            arr = m2.group(1)
            # Rough count of commas +1
            return arr.count(',') + 1 if arr.strip() != '[]' else 0
    except Exception:
        return None
    return None


def update_audit_summary(audit_path: Path, total: int, latest_score: float) -> None:
    if not audit_path.exists():
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text("# Audit Summary\n\n", encoding="utf-8")
    content = audit_path.read_text(encoding="utf-8")
    begin = "<!-- INTEGRITY_REGISTRY:BEGIN -->"
    end = "<!-- INTEGRITY_REGISTRY:END -->"
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    section = (
        f"{begin}\n"
        f"Updated: {timestamp}\n"
        f"📘 Integrity registry updated — {total} total entries tracked (latest score: {latest_score:.1f}%).\n"
        f"{end}"
    )
    if begin in content and end in content:
        import re
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
        content = pattern.sub(section, content)
    else:
        content = content.rstrip() + "\n\n" + section + "\n"
    audit_path.write_text(content, encoding="utf-8")


def append_registry_row(csv_path: Path, row: Dict[str, Any]) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    exists = csv_path.exists()
    if not exists:
        csv_path.write_text(",".join(REGISTRY_HEADER) + "\n", encoding="utf-8")
    # Count existing (excluding header)
    if exists:
        prev_lines = [
            l for l in csv_path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("#")
        ]
        # exclude header row if present
        count = max(0, len(prev_lines) - 1)
    else:
        count = 0
    line = ",".join([
        row.get("timestamp", ""),
        f"{row.get('integrity_score', 0):.1f}",
        str(row.get("violations", 0)),
        str(row.get("warnings", 0)),
        f"{row.get('health_score', 0):.1f}",
        f"{row.get('rri', 0):.1f}",
        f"{row.get('mpi', 0):.1f}",
        f"{row.get('confidence', 0):.3f}",
        row.get("status", "ok"),
    ])
    with csv_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return count + 1


def build_row(
    integrity: Dict[str, Any],
    self_audit: Dict[str, Any],
    reinforcement: Dict[str, Any]
) -> Dict[str, Any]:
    raw_ts = integrity.get("timestamp")
    timestamp = None
    if isinstance(raw_ts, str):
        try:
            parsed_ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            timestamp = parsed_ts.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            timestamp = raw_ts
    if not timestamp:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    integrity_score = safe_float(integrity.get("integrity_score"), 0.0)
    violations = int(integrity.get("violations", 0))
    warnings_count = len(integrity.get("warnings", [])) if isinstance(integrity.get("warnings"), list) else 0
    health_score = safe_float(self_audit.get("health_score"), 0.0)
    rri = safe_float(reinforcement.get("rri"), 0.0)
    # MPI & Confidence from self audit components if present
    components = self_audit.get("components", {}) if isinstance(self_audit, dict) else {}
    mpi = safe_float(components.get("mpi", {}).get("value") if isinstance(components.get("mpi"), dict) else components.get("mpi"), 0.0)
    confidence = safe_float(components.get("confidence", {}).get("value") if isinstance(components.get("confidence"), dict) else components.get("confidence"), 0.0)
    status = integrity.get("status", "ok")
    return {
        "timestamp": timestamp,
        "integrity_score": integrity_score,
        "violations": violations,
        "warnings": warnings_count,
        "health_score": health_score,
        "rri": rri,
        "mpi": mpi,
        "confidence": confidence,
        "status": status,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Integrity Metrics Registry")
    parser.add_argument("--integrity", type=Path, default=Path("reports/reflex_integrity.json"))
    parser.add_argument(
        "--self-audit",
        "--health",
        dest="self_audit",
        type=Path,
        default=Path("reports/reflex_self_audit.json"),
    )
    parser.add_argument("--reinforcement", type=Path, default=Path("reports/reflex_reinforcement.json"))
    parser.add_argument("--dashboard", type=Path, default=Path("reports/reflex_health_dashboard.html"))
    parser.add_argument("--output", type=Path, default=Path("exports/integrity_metrics_registry.csv"))
    parser.add_argument("--audit-summary", type=Path, default=Path("reports/audit_summary.md"))
    args = parser.parse_args(argv)

    try:
        integrity = load_json(args.integrity, default={})
        self_audit = load_json(args.self_audit, default={})
        reinforcement = load_json(args.reinforcement, default={})

        row = build_row(integrity, self_audit, reinforcement)
        total = append_registry_row(args.output, row)
        update_audit_summary(args.audit_summary, total, row["integrity_score"])

        cycle_count = parse_cycle_count(args.dashboard) or 0

        print(json.dumps({
            "status": "ok",
            "entries": total,
            "latest": row,
            "cycles": cycle_count
        }, indent=2))
        return 0
    except Exception as e:
        # Non-fatal; still exit 0
        print(json.dumps({"status": "error", "error": str(e)}))
        return 0

if __name__ == "__main__":
    sys.exit(main())
