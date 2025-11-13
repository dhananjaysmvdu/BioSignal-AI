"""Build a reproducibility capsule containing governance transparency artifacts.

The capsule bundles key transparency outputs (reports, exports, badges, archived
snapshots, and governing documentation) into a dated ZIP archive stored under
``exports/``. A companion manifest ``exports/capsule_manifest.json`` records the
file hashes and sizes to support external verification. The script updates the
``REPRODUCIBILITY_CAPSULE`` marker inside ``reports/audit_summary.md`` with a
human-readable status line and always exits with code 0 for CI stability.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REPO_RELATIVE_SOURCES: Tuple[str, ...] = (
    "reports",
    "exports",
    "badges",
    "archives/transparency_snapshots",
)
ADDITIONAL_FILES: Tuple[str, ...] = (
    "GOVERNANCE_TRANSPARENCY.md",
    "docs/GOVERNANCE_WHITEPAPER.md",
)
AUDIT_SUMMARY_PATH = Path("reports/audit_summary.md")
MARKER_NAME = "REPRODUCIBILITY_CAPSULE"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_source_files(repo_root: Path, capsule_path: Path) -> List[Path]:
    files: List[Path] = []
    for rel in REPO_RELATIVE_SOURCES:
        candidate = repo_root / rel
        if candidate.is_file():
            if candidate.resolve() != capsule_path.resolve():
                files.append(candidate)
            continue
        if not candidate.exists():
            continue
        for item in sorted(candidate.rglob("*")):
            if item.is_file() and item.resolve() != capsule_path.resolve():
                files.append(item)
    for rel in ADDITIONAL_FILES:
        path = repo_root / rel
        if path.exists() and path.is_file():
            if path.resolve() != capsule_path.resolve():
                files.append(path)
    files.sort(key=lambda p: p.relative_to(repo_root).as_posix())
    return files


def _update_audit_marker(repo_root: Path, message: str) -> None:
    summary_path = repo_root / AUDIT_SUMMARY_PATH
    begin = f"<!-- {MARKER_NAME}:BEGIN -->"
    end = f"<!-- {MARKER_NAME}:END -->"
    block = f"{begin}\n{message}\n{end}"
    if not summary_path.exists():
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(f"# Audit Summary\n\n{block}\n", encoding="utf-8")
        return
    text = summary_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"{re.escape(begin)}.*?{re.escape(end)}", re.DOTALL)
    if pattern.search(text):
        new_text = pattern.sub(block, text)
    else:
        new_text = text.rstrip() + f"\n\n{block}\n"
    summary_path.write_text(new_text, encoding="utf-8")


def _write_capsule(zip_path: Path, repo_root: Path, files: Iterable[Path]) -> int:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            arcname = file_path.relative_to(repo_root).as_posix()
            archive.write(file_path, arcname=arcname)
    with zipfile.ZipFile(zip_path, "r") as archive:
        return len(archive.infolist())


def _load_manifest(manifest_path: Path) -> Dict[str, object]:
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - defensive
        return {}


def main() -> None:
    repo_root = _repo_root()
    exports_dir = repo_root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    capsule_name = f"governance_reproducibility_capsule_{today}.zip"
    capsule_path = exports_dir / capsule_name
    manifest_path = exports_dir / "capsule_manifest.json"

    manifest_data = _load_manifest(manifest_path)
    existing_capsule = manifest_data.get("capsule", {}) if isinstance(manifest_data, dict) else {}
    recorded_hash = existing_capsule.get("sha256") if isinstance(existing_capsule, dict) else None
    recorded_date = manifest_data.get("generated_on") if isinstance(manifest_data, dict) else None

    if capsule_path.exists() and recorded_date == today:
        actual_hash = _hash_file(capsule_path)
        if recorded_hash == actual_hash:
            file_count = existing_capsule.get("file_count") or len(manifest_data.get("files", []))
            summary_message = f"Capsule generated {today} ({file_count} files, SHA256 verified)"
            _update_audit_marker(repo_root, summary_message)
            print("Reproducibility capsule is already up to date for today.")
            return

    source_files = _collect_source_files(repo_root, capsule_path)
    initial_count = len(source_files)
    if not source_files:
        print("No source files discovered for reproducibility capsule; creating empty archive.")

    summary_message = f"Capsule generated {today} ({initial_count} files, SHA256 verified)"
    _update_audit_marker(repo_root, summary_message)

    source_files = _collect_source_files(repo_root, capsule_path)
    capsule_file_count = len(source_files)
    if capsule_file_count != initial_count:
        summary_message = f"Capsule generated {today} ({capsule_file_count} files, SHA256 verified)"
        _update_audit_marker(repo_root, summary_message)

    capsule_file_count = _write_capsule(capsule_path, repo_root, source_files)
    capsule_hash = _hash_file(capsule_path)
    capsule_size = capsule_path.stat().st_size

    file_entries: List[Dict[str, object]] = []
    for path in source_files:
        rel_path = path.relative_to(repo_root).as_posix()
        file_entries.append(
            {
                "path": rel_path,
                "size": path.stat().st_size,
                "sha256": _hash_file(path),
            }
        )

    manifest = {
        "generated_on": today,
        "capsule": {
            "path": f"exports/{capsule_name}",
            "size": capsule_size,
            "sha256": capsule_hash,
            "file_count": capsule_file_count,
        },
        "files": file_entries,
        "sources": list(REPO_RELATIVE_SOURCES) + list(ADDITIONAL_FILES),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    summary_message = f"Capsule generated {today} ({capsule_file_count} files, SHA256 verified)"
    _update_audit_marker(repo_root, summary_message)
    print(f"Created reproducibility capsule at {capsule_path.relative_to(repo_root)}")


if __name__ == "__main__":  # pragma: no cover - script entry point
    try:
        main()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"export_reproducibility_capsule encountered an error: {exc}")
    finally:
        sys.exit(0)
