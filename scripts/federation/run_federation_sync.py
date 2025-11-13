"""Run the BioSignal-AI Global Reproducibility Federation sync.

This script simulates querying trusted federation nodes (Zenodo, GitHub, OpenAIRE, arXiv)
for release metadata (DOI, release version, hash proofs) and computes the Federation
Integrity Index (FII).

The implementation is designed to be deterministic and auditable:
- Loads the reference manifest declared in ``federation_config.json``
- Synthesises node responses based on the reference data plus configured latency
- Records any mismatches or latency-derived drift to ``federation_drift_log.jsonl``
- Emits a summary JSON snapshot for downstream dashboards

The FII is defined as ``100 - drift_percent`` where ``drift_percent`` combines propagation
latency (relative to sync interval) and structural mismatches (hash/DOI/release).
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "federation" / "federation_config.json"
DRIFT_LOG_PATH = REPO_ROOT / "federation" / "federation_drift_log.jsonl"
STATUS_PATH = REPO_ROOT / "federation" / "federation_status.json"


def load_config() -> Dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_reference_manifest(manifest_path: Path) -> Dict:
    with manifest_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def synthesize_node_response(node: str, reference: Dict) -> Dict:
    """Create a deterministic pseudo-response for the given node.

    For production the implementation would call out to REST endpoints. Here we mirror
    the reference data so governance artifacts remain consistent while exposing minor
    propagation differences for monitoring.
    """

    response = {
        "node": node,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "doi": reference.get("doi"),
        "release": reference.get("release"),
        "release_hash": reference.get("capsule_hash_proofs", [{}])[0].get("sha256"),
        "metadata_hash": reference.get("capsule_hash_proofs", [{}])[0].get("sha256"),
        "extra_checks": {
            "integrity_score": reference.get("integrity_score"),
            "reproducibility_status": reference.get("reproducibility_status"),
        },
    }

    # Introduce minimal, node-specific variance that represents propagation latency.
    # These fields are encoded downstream when computing drift.
    response["propagation_latency_hours"] = reference.get("propagation_latency_override", {}).get(node)

    return response


def compute_drift(
    config: Dict,
    responses: List[Dict],
    reference: Dict,
) -> Tuple[float, List[Dict]]:
    """Compute drift percentage and capture detailed findings per node."""

    sync_interval_hours = parse_sync_interval(config.get("sync_interval", "24h"))
    baseline_latency = config.get("baseline_latency_hours", {})
    findings: List[Dict] = []
    total_latency = 0.0
    total_checks = 0
    mismatch_count = 0

    reference_release = reference.get("release")
    reference_doi = reference.get("doi")
    reference_hash = reference.get("capsule_hash_proofs", [{}])[0].get("sha256")

    for entry in responses:
        node = entry["node"]
        latency = baseline_latency.get(node, 0.0)
        if entry.get("propagation_latency_hours") is None:
            entry["propagation_latency_hours"] = latency
        else:
            latency = entry["propagation_latency_hours"]

        total_latency += latency

        node_findings = {
            "node": node,
            "latency_hours": round(latency, 3),
            "checks": {},
        }

        # DOI check
        node_findings["checks"]["doi_match"] = entry.get("doi") == reference_doi
        total_checks += 1
        if not node_findings["checks"]["doi_match"]:
            mismatch_count += 1

        # Release version check
        node_findings["checks"]["release_match"] = entry.get("release") == reference_release
        total_checks += 1
        if not node_findings["checks"]["release_match"]:
            mismatch_count += 1

        # Hash check
        node_findings["checks"]["hash_match"] = entry.get("release_hash") == reference_hash
        total_checks += 1
        if not node_findings["checks"]["hash_match"]:
            mismatch_count += 1

        findings.append(node_findings)

    latency_component = 0.0
    if sync_interval_hours and responses:
        latency_component = (total_latency / (sync_interval_hours * len(responses))) * 100.0

    mismatch_component = 0.0
    if total_checks:
        mismatch_component = (mismatch_count / total_checks) * 100.0

    drift_percent = round(latency_component + mismatch_component, 3)
    return drift_percent, findings


def parse_sync_interval(interval: str) -> float:
    if not interval:
        return 24.0
    interval = interval.strip().lower()
    if interval.endswith("h"):
        return float(interval[:-1])
    if interval.endswith("m"):
        return float(interval[:-1]) / 60.0
    if interval.endswith("d"):
        return float(interval[:-1]) * 24.0
    return float(interval)


def append_log_entry(data: Dict) -> None:
    DRIFT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DRIFT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data) + "\n")


def write_status_snapshot(data: Dict) -> None:
    with STATUS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def run() -> Dict:
    config = load_config()
    reference_manifest_path = REPO_ROOT / config.get("reference_manifest", "verification_gateway/public_verification_api.json")
    if not reference_manifest_path.exists():
        raise FileNotFoundError(f"Reference manifest not found: {reference_manifest_path}")

    reference = load_reference_manifest(reference_manifest_path)

    responses = [synthesize_node_response(node, reference) for node in config.get("trusted_nodes", [])]

    drift_percent, findings = compute_drift(config, responses, reference)
    fii = round(max(0.0, 100.0 - drift_percent), 3)

    timestamp = datetime.now(timezone.utc).isoformat()

    log_entry = {
        "timestamp": timestamp,
        "federation_id": config.get("federation_id"),
        "reference_release": reference.get("release"),
        "doi": reference.get("doi"),
        "drift_percent": drift_percent,
        "federation_integrity_index": fii,
        "nodes": findings,
    }

    append_log_entry(log_entry)
    write_status_snapshot(log_entry)

    logging.info("Federation Integrity Index (FII): %.3f", fii)
    return log_entry


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Global Reproducibility Federation sync")
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the computed federation status to stdout",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    parser = build_cli()
    args = parser.parse_args()

    status = run()
    if args.print:
        print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
