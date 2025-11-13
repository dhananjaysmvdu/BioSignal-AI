#!/usr/bin/env python3
"""
Generate Public Verification Gateway API

Exposes for external reproducibility validation:
- Latest DOI, tag, release version
- Integrity and reproducibility status
- CE, FB, FDI, CS metrics
- Capsule SHA256 proofs from capsule_manifest.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]

PORTAL_METRICS = ROOT / "portal" / "metrics.json"
CAPSULE_MANIFEST = ROOT / "exports" / "capsule_manifest.json"
README = ROOT / "README.md"
DECISION_TRACE = ROOT / "exports" / "decision_trace_log.jsonl"
ETHICS_REPORTS_DIR = ROOT / "reports" / "ethics"
OUTPUT = ROOT / "verification_gateway" / "public_verification_api.json"


def read_json_safe(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def extract_doi_from_readme() -> Optional[str]:
    if not README.exists():
        return None
    txt = README.read_text(encoding="utf-8", errors="ignore")
    import re
    m = re.search(r"10\.\d{4,9}/[A-Za-z0-9._;()/:\-]+", txt)
    return m.group(0) if m else None


def load_ethics_data() -> dict:
    """Load latest ethics compliance data."""
    if not ETHICS_REPORTS_DIR.exists():
        return {
            "bias_score": None,
            "fairness_status": "pending",
            "ethics_last_checked": None,
            "ethics_report_hash": None,
        }
    
    # Find latest ethics report
    reports = sorted(ETHICS_REPORTS_DIR.glob("ethics_compliance_*.json"))
    if not reports:
        return {
            "bias_score": None,
            "fairness_status": "pending",
            "ethics_last_checked": None,
            "ethics_report_hash": None,
        }
    
    latest_report = reports[-1]
    try:
        data = json.loads(latest_report.read_text(encoding="utf-8"))
        bias_analysis = data.get("bias_analysis", {})
        return {
            "bias_score": bias_analysis.get("bias_score"),
            "fairness_status": data.get("compliance_status", "unknown"),
            "ethics_last_checked": data.get("generated_at"),
            "ethics_report_hash": data.get("report_hash"),
        }
    except Exception:
        return {
            "bias_score": None,
            "fairness_status": "error",
            "ethics_last_checked": None,
            "ethics_report_hash": None,
        }


def get_latest_decision_trace_id() -> Optional[str]:
    """Get ID of most recent governance decision."""
    if not DECISION_TRACE.exists():
        return None
    
    try:
        with DECISION_TRACE.open("r", encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
            if not lines:
                return None
            last_entry = json.loads(lines[-1])
            return last_entry.get("id")
    except Exception:
        return None


def main() -> None:
    metrics = read_json_safe(PORTAL_METRICS)
    manifest = read_json_safe(CAPSULE_MANIFEST)

    doi = extract_doi_from_readme()
    integrity = metrics.get("integrity", {})
    repro = metrics.get("reproducibility", {})
    prov = metrics.get("provenance", {})
    cal = metrics.get("calibration", {})
    forecast = metrics.get("forecast_metrics", {})
    
    # Load ethics compliance data
    ethics = load_ethics_data()
    decision_trace_id = get_latest_decision_trace_id()

    # Build capsule proofs array (top-level capsule + first 5 files)
    capsule_proofs = []
    cap = manifest.get("capsule", {})
    if cap.get("sha256"):
        capsule_proofs.append({
            "path": cap.get("path", "exports/governance_reproducibility_capsule_<date>.zip"),
            "sha256": cap.get("sha256"),
            "size": cap.get("size"),
        })
    for f in manifest.get("files", [])[:5]:
        if f.get("sha256"):
            capsule_proofs.append({
                "path": f.get("path"),
                "sha256": f.get("sha256"),
                "size": f.get("size"),
            })

    api = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "doi": doi or repro.get("doi"),
        "release": prov.get("release", "v1.0.0-Whitepaper"),
        "release_date": prov.get("release_date"),
        "integrity_score": integrity.get("score"),
        "reproducibility_status": repro.get("status"),
        "calibration_error": cal.get("calibration_error"),
        "forecast_bias": cal.get("forecast_bias"),
        "fdi": forecast.get("fdi", {}).get("value"),
        "cs": forecast.get("cs", {}).get("value"),
        "bias_score": ethics.get("bias_score"),
        "fairness_status": ethics.get("fairness_status"),
        "ethics_last_checked": ethics.get("ethics_last_checked"),
        "decision_trace_id": decision_trace_id,
        "ethics_report_hash": ethics.get("ethics_report_hash"),
        "capsule_hash_proofs": capsule_proofs,
        "verification_endpoints": {
            "portal_metrics": "https://raw.githubusercontent.com/dhananjaysmvdu/BioSignal-AI/main/portal/metrics.json",
            "capsule_manifest": "https://raw.githubusercontent.com/dhananjaysmvdu/BioSignal-AI/main/exports/capsule_manifest.json",
            "ethics_portal": "https://raw.githubusercontent.com/dhananjaysmvdu/BioSignal-AI/main/portal/ethics.html",
            "decision_trace": "https://raw.githubusercontent.com/dhananjaysmvdu/BioSignal-AI/main/exports/decision_trace_log.jsonl",
            "doi_link": f"https://doi.org/{doi}" if doi else None,
        }
    }

    OUTPUT.write_text(json.dumps(api, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Public Verification Gateway updated: {OUTPUT}")


if __name__ == "__main__":
    main()
