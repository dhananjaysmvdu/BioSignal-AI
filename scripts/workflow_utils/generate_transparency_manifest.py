#!/usr/bin/env python3
"""
Generate Governance Transparency Manifest

Produces a single human-readable markdown file (GOVERNANCE_TRANSPARENCY.md)
summarizing the current governance artifacts, their freshness, and key signals.

Behavior:
- Always exits 0 (CI-safe)
- Tolerates missing files; marks them as "missing"
- Includes recent integrity registry tail (up to 10 entries)
"""
from __future__ import annotations

import csv
import json
import argparse
import sys
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional


ARTIFACTS: List[Dict[str, Any]] = [
    {"path": Path("reports/audit_summary.md"), "label": "Audit Summary", "desc": "Consolidated audit run markers and notes"},
    {"path": Path("reports/reflex_integrity.json"), "label": "Reflex Integrity", "desc": "Integrity score, violations, and warnings"},
    {"path": Path("reports/reflex_self_audit.json"), "label": "Reflex Self-Audit", "desc": "Comprehensive reflex health and classification"},
    {"path": Path("reports/reflex_reinforcement.json"), "label": "Reflex Reinforcement", "desc": "Reinforcement index and alignment"},
    {"path": Path("reports/confidence_adaptation.json"), "label": "Confidence Adaptation", "desc": "Confidence-weighted adaptation details"},
    {"path": Path("reports/governance_health.json"), "label": "Governance Health", "desc": "Composite Governance Health Score (GHS)"},
    {"path": Path("exports/reflex_health_timeline.csv"), "label": "Health Timeline CSV", "desc": "Reflex health timeline export"},
    {"path": Path("reports/reflex_health_dashboard.html"), "label": "Health Dashboard", "desc": "HTML dashboard with reflex health charts"},
    {"path": Path("exports/integrity_metrics_registry.csv"), "label": "Integrity Metrics Registry", "desc": "Longitudinal integrity metrics for analytics"},
    {"path": Path("reports/provenance_dashboard.html"), "label": "Provenance Dashboard", "desc": "Governance pulse dashboard"},
    {"path": Path("configs/governance_policy.json"), "label": "Governance Policy", "desc": "Adaptive governance coefficients and thresholds"},
]


def read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def fmt_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return ""


def csv_tail(p: Path, n: int = 10) -> List[List[str]]:
    if not p.exists():
        return []
    try:
        rows: List[List[str]] = []
        with p.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            all_rows = list(reader)
        if not all_rows:
            return []
        header, data = all_rows[0], all_rows[1:]
        tail = data[-n:]
        return [header] + tail
    except Exception:
        return []


def load_integrity_summary(p: Path) -> str:
    data = read_json(p)
    if not isinstance(data, dict):
        return ""
    score = data.get("integrity_score")
    vio = data.get("violations")
    if score is None:
        return ""
    return f"Integrity Score: {score}% — Violations: {vio}"


def build_manifest() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines: List[str] = []
    lines.append("# Governance Transparency Manifest")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append("")

    # Overview: highlight integrity quick status if present
    integ_line = load_integrity_summary(Path("reports/reflex_integrity.json"))
    if integ_line:
        lines.append(f"- {integ_line}")
    lines.append("")

    # Artifacts table
    lines.append("## Artifacts")
    lines.append("")
    lines.append("Name | Status | Updated (UTC) | Size | Notes")
    lines.append("---|---|---:|---:|---")
    for a in ARTIFACTS:
        p: Path = a["path"]
        label: str = a["label"]
        desc: str = a["desc"]
        if p.exists():
            status = "present"
            mtime = fmt_ts(p.stat().st_mtime)
            size = str(p.stat().st_size)
        else:
            status = "missing"
            mtime = ""
            size = "0"
        lines.append(f"{label} | {status} | {mtime} | {size} | {desc}")

    # Integrity Registry (tail)
    reg = Path("exports/integrity_metrics_registry.csv")
    reg_tail = csv_tail(reg, 10)
    lines.append("")
    lines.append("## Integrity Metrics Registry (last 10)")
    lines.append("")
    if reg_tail:
        header = reg_tail[0]
        lines.append(" | ".join(header))
        lines.append(" | ".join(["---"] * len(header)))
        for row in reg_tail[1:]:
            # pad/truncate to header length
            row = (row + [""] * len(header))[: len(header)]
            normalized = row.copy()
            if normalized:
                ts_value = normalized[0]
                if isinstance(ts_value, str) and ts_value.endswith("Z"):
                    normalized[0] = ts_value[:-1] + "+00:00"
            lines.append(" | ".join(normalized))
    else:
        lines.append("No registry entries available.")

    # Audit markers snapshot (optional)
    audit_p = Path("reports/audit_summary.md")
    if audit_p.exists():
        lines.append("")
        lines.append("## Audit Markers Snapshot")
        lines.append("")
        try:
            content = audit_p.read_text(encoding="utf-8")
            # Extract only lines with markers for brevity
            snippet = "\n".join([ln for ln in content.splitlines() if ln.strip().startswith("<!-- ") or ln.strip().startswith("🧩") or ln.strip().startswith("🔍") or ln.strip().startswith("🧭") or ln.strip().startswith("📘")])
            if snippet.strip():
                lines.append("```")
                lines.append(snippet)
                lines.append("```")
        except Exception:
            pass

    lines.append("")
    # Data Schema appendix
    lines.append("---")
    lines.append("## Data Schema")
    canonical = [
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
    schema_hash = hashlib.sha256(",".join(canonical).encode("utf-8")).hexdigest()
    lines.append(
        "integrity_metrics_registry.csv:  " + ", ".join(canonical)
    )
    lines.append(
        "audit_summary.md markers:  REFLEX_POLICY, REFLEX_META, REFLEX_FORECAST, CONFIDENCE_ADAPTATION, REFLEX_REINFORCEMENT, REFLEX_SELF_AUDIT, REFLEX_INTEGRITY, REFLEX_HEALTH_DASHBOARD, INTEGRITY_REGISTRY, INTEGRITY_REGISTRY_SCHEMA, TRANSPARENCY_MANIFEST"
    )
    lines.append(f"Schema hash: {schema_hash}")

    # API Endpoints appendix
    lines.append("\n## API Endpoints")
    lines.append("- badges/integrity_status.json — current mean integrity score (for external dashboards)")
    lines.append("- exports/schema_provenance_ledger.jsonl — schema history (immutable ledger)")

    # Citation & Research Export block
    lines.append("\n## Citation & Research Export")
    lines.append("")
    lines.append("If you use or build on this governance reflex architecture, please cite:")
    lines.append("")
    lines.append("> Reflex Governance Architecture: Self-Verifying Adaptive Control System, v1.0  ")
    lines.append("> DOI: https://doi.org/10.5281/zenodo.14173152  ")
    lines.append("> Repository: https://github.com/dhananjaysmvdu/BioSignal-AI")
    lines.append("")
    lines.append("### Research Export Artifacts")
    lines.append("- exports/integrity_metrics_registry.csv — full longitudinal metrics trace")
    lines.append("- exports/schema_provenance_ledger.jsonl — append-only schema ledger")
    lines.append("- badges/integrity_status.json — nightly integrity score (for dashboards)")
    lines.append("- GOVERNANCE_TRANSPARENCY.md — human-readable system manifest")

    lines.append("\n---")
    lines.append("This file is auto-generated; do not edit manually.")
    return "\n".join(lines) + "\n"


def update_audit_summary(audit_path: Path, manifest_path: Path) -> None:
    if audit_path is None:
        return
    if not audit_path.exists():
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text("# Audit Summary\n\n", encoding="utf-8")

    content = audit_path.read_text(encoding="utf-8")
    begin = "<!-- TRANSPARENCY_MANIFEST:BEGIN -->"
    end = "<!-- TRANSPARENCY_MANIFEST:END -->"
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    size = manifest_path.stat().st_size if manifest_path.exists() else 0
    section = (
        f"{begin}\n"
        f"Updated: {timestamp}\n"
        f"📄 Governance transparency manifest refreshed — {size} bytes written.\n"
        f"{end}"
    )
    if begin in content and end in content:
        import re
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
        content = pattern.sub(section, content)
    else:
        content = content.rstrip() + "\n\n" + section + "\n"
    audit_path.write_text(content, encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Governance Transparency Manifest")
    parser.add_argument("--output", type=Path, default=Path("GOVERNANCE_TRANSPARENCY.md"))
    parser.add_argument("--audit-summary", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        manifest = build_manifest()
        args.output.write_text(manifest, encoding="utf-8")
        if args.audit_summary is not None:
            update_audit_summary(args.audit_summary, args.output)
        print(json.dumps({"status": "ok", "path": str(args.output)}))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
