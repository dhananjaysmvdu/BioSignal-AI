"""Propagate Zenodo DOI placeholders across governance documentation.

Reads the DOI value from either ``zenodo.json`` or ``zenodo_metadata.json`` and
updates public-facing documentation files so the latest DOI is displayed. The
script stages and commits any resulting changes with the commit message
``docs: propagate Zenodo DOI across governance documentation``. It always exits
with status code 0 for CI safety.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

COMMIT_MESSAGE = "docs: propagate Zenodo DOI across governance documentation"
PLACEHOLDER_STRINGS = (
    "(to be assigned via Zenodo)",
    "(to be assigned via Zenodo upon first release)",
    "(to be assigned via Zenodo upon v1.0.0-Whitepaper release)",
)
TARGET_FILES = (
    Path("README.md"),
    Path("docs/GOVERNANCE_WHITEPAPER.md"),
    Path("scripts/workflow_utils/generate_transparency_manifest.py"),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_doi(repo_root: Path) -> Tuple[Optional[str], Optional[Path]]:
    for candidate in ("zenodo.json", "zenodo_metadata.json"):
        candidate_path = repo_root / candidate
        if not candidate_path.exists():
            continue
        try:
            data = json.loads(candidate_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Unable to parse {candidate_path}: {exc}")
            continue
        doi = data.get("doi") or data.get("metadata", {}).get("doi")
        if doi:
            return doi.strip(), candidate_path
    return None, None


def _normalise_doi(raw_doi: str) -> str:
    doi = raw_doi.strip()
    if not doi:
        return doi
    if doi.lower().startswith("http://") or doi.lower().startswith("https://"):
        return doi
    return f"https://doi.org/{doi}"


def _replace_placeholders(text: str, doi_value: str) -> Tuple[str, bool]:
    updated = text
    changed = False
    for placeholder in PLACEHOLDER_STRINGS:
        if placeholder in updated:
            updated = updated.replace(placeholder, doi_value)
            changed = True
    return updated, changed


def _update_readme(text: str, doi_value: str) -> Tuple[str, bool]:
    pattern = re.compile(r"(^> DOI:\s*)(.+)$", re.MULTILINE)

    def repl(match: re.Match[str]) -> str:
        return f"{match.group(1)}{doi_value}"

    new_text, count = pattern.subn(repl, text, count=1)
    if count:
        return new_text, True
    return _replace_placeholders(text, doi_value)


def _update_whitepaper(text: str, doi_value: str) -> Tuple[str, bool]:
    pattern = re.compile(r"(^\*\*DOI:\*\*\s*)(.+)$", re.MULTILINE)

    def repl(match: re.Match[str]) -> str:
        return f"{match.group(1)}{doi_value}"

    new_text, count = pattern.subn(repl, text, count=1)
    if count:
        return new_text, True
    return _replace_placeholders(text, doi_value)


def _update_manifest_script(text: str, doi_value: str) -> Tuple[str, bool]:
    pattern = re.compile(r"(lines\.append\(\"> DOI: )(.*?)(  \"\))")

    def repl(match: re.Match[str]) -> str:
        return f"{match.group(1)}{doi_value}{match.group(3)}"

    new_text, count = pattern.subn(repl, text)
    if count:
        return new_text, True
    return _replace_placeholders(text, doi_value)


_UPDATERS: Dict[Path, Callable[[str, str], Tuple[str, bool]]] = {
    TARGET_FILES[0]: _update_readme,
    TARGET_FILES[1]: _update_whitepaper,
    TARGET_FILES[2]: _update_manifest_script,
}


def _stage_paths(paths: Iterable[Path]) -> None:
    repo_root = _repo_root()
    for path in paths:
        rel = path.relative_to(repo_root)
        subprocess.run(["git", "add", str(rel)], check=False)


def _commit_if_needed() -> None:
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        print("No changes detected; nothing to commit.")
        return
    result = subprocess.run(["git", "commit", "-m", COMMIT_MESSAGE], check=False)
    if result.returncode != 0:
        print("Git commit failed; manual intervention may be required.")


def main() -> None:
    repo_root = _repo_root()
    doi_value, source_path = _load_doi(repo_root)
    if not doi_value:
        print("No DOI value found in zenodo metadata; nothing to update.")
        return
    doi_value = _normalise_doi(doi_value)
    print(f"Updating documentation with DOI: {doi_value}")
    print(f"DOI source: {source_path}")

    changed_files: List[Path] = []
    for target, updater in _UPDATERS.items():
        file_path = repo_root / target
        if not file_path.exists():
            continue
        original = file_path.read_text(encoding="utf-8")
        updated, changed = updater(original, doi_value)
        if changed and updated != original:
            file_path.write_text(updated, encoding="utf-8")
            changed_files.append(file_path)
            print(f"Updated {file_path.relative_to(repo_root)}")

    if not changed_files:
        print("No documentation updates required.")
        return

    _stage_paths(changed_files)
    _commit_if_needed()


if __name__ == "__main__":  # pragma: no cover - script entry point
    try:
        main()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"update_doi_reference encountered an error: {exc}")
    finally:
        sys.exit(0)
