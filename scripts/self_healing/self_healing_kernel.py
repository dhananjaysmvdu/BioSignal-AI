"""Autonomous self-healing kernel for governance artifacts.

The kernel verifies critical governance artifacts against a recovery manifest,
restores any missing or corrupted files from the git history, and logs the
outcome to ``self_healing/self_healing_log.jsonl``.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "self_healing" / "recovery_manifest.json"
LOG_PATH = ROOT / "self_healing" / "self_healing_log.jsonl"
SUMMARY_PATH = ROOT / "self_healing" / "self_healing_summary.json"

# Files that must always be recoverable. Extend this list as the governance
# footprint grows.
MONITORED_PATHS: List[str] = [
    "GOVERNANCE_TRANSPARENCY.md",
    "audit_summary.md",
    "verification_gateway/public_verification_api.json",
    "PHASE_VIII_COMPLETION_REPORT.md",
]


@dataclass
class ManifestEntry:
    path: str
    ref: str
    expected_hash: str


def _compute_sha256(path: Path) -> str:
    data = path.read_bytes()
    return sha256(data).hexdigest()


def _load_manifest() -> Dict[str, ManifestEntry]:
    if not MANIFEST_PATH.exists():
        return {}
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    entries: Dict[str, ManifestEntry] = {}
    for item in payload.get("entries", []):
        entries[item["path"]] = ManifestEntry(
            path=item["path"],
            ref=item["ref"],
            expected_hash=item["expected_hash"],
        )
    return entries


def _write_manifest(entries: Iterable[ManifestEntry]) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entries": [entry.__dict__ for entry in entries],
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)


def _git_show(ref: str, file_path: str) -> Optional[bytes]:
    """Return file bytes from git history, or None if lookup fails."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{file_path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def _append_log(entry: Dict[str, object]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _ensure_manifest(refresh: bool = False) -> Dict[str, ManifestEntry]:
    entries = _load_manifest()
    if entries and not refresh:
        return entries

    manifest_entries: List[ManifestEntry] = []
    ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    for relative_path in MONITORED_PATHS:
        file_path = ROOT / relative_path
        if not file_path.exists():
            # Attempt to populate missing file from git when creating baseline.
            blob = _git_show(ref, relative_path)
            if blob is not None:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(blob)
        if file_path.exists():
            manifest_entries.append(
                ManifestEntry(
                    path=relative_path,
                    ref=ref,
                    expected_hash=_compute_sha256(file_path),
                )
            )
    _write_manifest(manifest_entries)
    _append_log(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "manifest_refreshed",
            "entry_count": len(manifest_entries),
            "ref": ref,
        }
    )
    return {entry.path: entry for entry in manifest_entries}


def _restore_file(entry: ManifestEntry) -> bool:
    blob = _git_show(entry.ref, entry.path)
    if blob is None:
        return False
    target = ROOT / entry.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob)
    return _compute_sha256(target) == entry.expected_hash


def main(refresh_manifest: bool = False) -> Dict[str, object]:
    manifest_entries = _ensure_manifest(refresh_manifest)
    timestamp = datetime.now(timezone.utc).isoformat()

    issues_detected = 0
    issues_recovered = 0

    for entry in manifest_entries.values():
        target = ROOT / entry.path
        issue_type: Optional[str] = None
        if not target.exists():
            issue_type = "missing"
        else:
            current_hash = _compute_sha256(target)
            if current_hash != entry.expected_hash:
                issue_type = "hash_mismatch"
        if issue_type:
            issues_detected += 1
            restored = _restore_file(entry)
            if restored:
                issues_recovered += 1
            _append_log(
                {
                    "timestamp": timestamp,
                    "event": "self_healing",
                    "path": entry.path,
                    "issue_type": issue_type,
                    "restored": restored,
                }
            )
        else:
            _append_log(
                {
                    "timestamp": timestamp,
                    "event": "verification",
                    "path": entry.path,
                    "status": "healthy",
                }
            )

    recovery_rate = 1.0 if issues_detected == 0 else issues_recovered / issues_detected
    summary = {
        "timestamp": timestamp,
        "monitored_files": len(manifest_entries),
        "issues_detected": issues_detected,
        "issues_recovered": issues_recovered,
        "recovery_rate": round(recovery_rate * 100, 2),
    }

    _append_log({"summary": summary})
    with SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the self-healing kernel")
    parser.add_argument(
        "--refresh-manifest",
        action="store_true",
        help="Rebuild the recovery manifest before running integrity checks.",
    )
    args = parser.parse_args()
    main(refresh_manifest=args.refresh_manifest)
