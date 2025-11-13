"""Verify DOI and capsule tag cross-references in governance documentation.

This script ensures that the latest Zenodo DOI and reproducibility capsule tag
are properly referenced in key governance documents (whitepaper and transparency
manifest). It performs soft validation, printing status messages and always
exiting with code 0 for CI safety.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _get_latest_doi(repo_root: Path) -> Tuple[Optional[str], Optional[str]]:
    """Read DOI from zenodo_metadata.json or zenodo.json."""
    for candidate in ("zenodo.json", "zenodo_metadata.json"):
        candidate_path = repo_root / candidate
        if not candidate_path.exists():
            continue
        try:
            # Try UTF-8 first, then UTF-8-SIG to handle BOM
            for encoding in ("utf-8", "utf-8-sig"):
                try:
                    data = json.loads(candidate_path.read_text(encoding=encoding))
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError(f"Unable to decode {candidate}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"⚠️  Unable to parse {candidate}: {exc}")
            continue
        doi = data.get("doi") or data.get("metadata", {}).get("doi")
        if doi:
            # Normalize DOI to URL format
            doi_str = doi.strip()
            if not doi_str.lower().startswith("http"):
                doi_str = f"https://doi.org/{doi_str}"
            return doi_str, candidate
    return None, None


def _get_latest_capsule_tag() -> Tuple[Optional[str], Optional[str]]:
    """Get the most recent capsule-* tag and its commit SHA."""
    try:
        result = subprocess.run(
            ["git", "tag", "--list", "capsule-*", "--sort=-creatordate"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None, None
        latest_tag = result.stdout.strip().split("\n")[0]
        
        # Get commit SHA for tag
        sha_result = subprocess.run(
            ["git", "rev-parse", "--short", latest_tag],
            capture_output=True,
            text=True,
            check=False,
        )
        commit_sha = sha_result.stdout.strip() if sha_result.returncode == 0 else None
        return latest_tag, commit_sha
    except Exception as exc:  # pragma: no cover - defensive
        print(f"⚠️  Unable to retrieve capsule tags: {exc}")
        return None, None


def _check_doi_in_file(file_path: Path, doi: str) -> bool:
    """Check if DOI appears in the specified file."""
    if not file_path.exists():
        return False
    try:
        content = file_path.read_text(encoding="utf-8")
        # Extract just the DOI identifier (10.5281/zenodo.XXXXXX)
        doi_match = re.search(r"10\.\d{4,}/zenodo\.\d+", doi)
        if doi_match:
            doi_id = doi_match.group(0)
            return doi_id in content
        return doi in content
    except Exception:  # pragma: no cover - defensive
        return False


def _check_capsule_in_file(file_path: Path, capsule_tag: str) -> bool:
    """Check if capsule tag appears in the specified file."""
    if not file_path.exists():
        return False
    try:
        content = file_path.read_text(encoding="utf-8")
        return capsule_tag in content
    except Exception:  # pragma: no cover - defensive
        return False


def _format_status(check_passed: bool) -> str:
    return "✅" if check_passed else "❌"


def main() -> None:
    repo_root = _repo_root()
    
    print("=" * 70)
    print("RELEASE INTEGRITY VERIFICATION")
    print("=" * 70)
    
    # Check DOI
    doi, doi_source = _get_latest_doi(repo_root)
    if doi:
        print(f"\n📄 DOI Found: {doi}")
        print(f"   Source: {doi_source}")
    else:
        print("\n⚠️  No DOI found in zenodo metadata files")
        print("   This is expected before first Zenodo release.")
    
    # Check capsule tag
    capsule_tag, commit_sha = _get_latest_capsule_tag()
    if capsule_tag:
        print(f"\n📦 Latest Capsule Tag: {capsule_tag}")
        if commit_sha:
            print(f"   Commit SHA: {commit_sha}")
    else:
        print("\n⚠️  No capsule tags found")
        print("   Run workflow manually to create first capsule tag.")
    
    # Verify cross-references
    print("\n" + "-" * 70)
    print("CROSS-REFERENCE VERIFICATION")
    print("-" * 70)
    
    whitepaper_path = repo_root / "docs" / "GOVERNANCE_WHITEPAPER.md"
    manifest_path = repo_root / "GOVERNANCE_TRANSPARENCY.md"
    
    checks = []
    
    if doi:
        whitepaper_doi = _check_doi_in_file(whitepaper_path, doi)
        manifest_doi = _check_doi_in_file(manifest_path, doi)
        
        checks.append(("DOI in GOVERNANCE_WHITEPAPER.md", whitepaper_doi))
        checks.append(("DOI in GOVERNANCE_TRANSPARENCY.md", manifest_doi))
        
        print(f"\n{_format_status(whitepaper_doi)} DOI in GOVERNANCE_WHITEPAPER.md")
        print(f"{_format_status(manifest_doi)} DOI in GOVERNANCE_TRANSPARENCY.md")
    else:
        print("\n⏭️  Skipping DOI checks (no DOI available)")
    
    if capsule_tag:
        whitepaper_capsule = _check_capsule_in_file(whitepaper_path, capsule_tag)
        manifest_capsule = _check_capsule_in_file(manifest_path, capsule_tag)
        
        # Extract just the date part for more flexible matching
        capsule_date = capsule_tag.replace("capsule-", "")
        whitepaper_date = _check_capsule_in_file(whitepaper_path, capsule_date)
        manifest_date = _check_capsule_in_file(manifest_path, capsule_date)
        
        # Pass if either full tag or date found
        whitepaper_check = whitepaper_capsule or whitepaper_date
        manifest_check = manifest_capsule or manifest_date
        
        checks.append(("Capsule tag in GOVERNANCE_WHITEPAPER.md", whitepaper_check))
        checks.append(("Capsule tag in GOVERNANCE_TRANSPARENCY.md", manifest_check))
        
        print(f"\n{_format_status(whitepaper_check)} Capsule tag/date in GOVERNANCE_WHITEPAPER.md")
        print(f"{_format_status(manifest_check)} Capsule tag/date in GOVERNANCE_TRANSPARENCY.md")
    else:
        print("\n⏭️  Skipping capsule checks (no capsule tags available)")
    
    # File existence checks
    print("\n" + "-" * 70)
    print("DOCUMENTATION FILE CHECKS")
    print("-" * 70)
    
    whitepaper_exists = whitepaper_path.exists()
    manifest_exists = manifest_path.exists()
    
    print(f"\n{_format_status(whitepaper_exists)} GOVERNANCE_WHITEPAPER.md exists")
    print(f"{_format_status(manifest_exists)} GOVERNANCE_TRANSPARENCY.md exists")
    
    checks.append(("GOVERNANCE_WHITEPAPER.md exists", whitepaper_exists))
    checks.append(("GOVERNANCE_TRANSPARENCY.md exists", manifest_exists))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if checks:
        passed = sum(1 for _, status in checks if status)
        total = len(checks)
        
        print(f"\nChecks Passed: {passed}/{total}")
        
        if passed == total:
            print("✅ All verification checks passed!")
        elif passed > 0:
            print("⚠️  Some checks failed - review output above")
        else:
            print("❌ All checks failed - verify governance setup")
    else:
        print("\n⚠️  No checks performed (missing DOI and capsule tags)")
        print("   This is expected before first release.")
    
    print("\n" + "=" * 70)
    print("Note: This is a soft check. Workflow will continue regardless of results.")
    print("=" * 70)


if __name__ == "__main__":  # pragma: no cover - script entry point
    try:
        main()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"verify_release_integrity encountered an error: {exc}")
    finally:
        sys.exit(0)  # Always exit 0 for CI safety
