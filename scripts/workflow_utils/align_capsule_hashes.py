#!/usr/bin/env python3
"""
Align Capsule Manifest Hashes

Ensures capsule_manifest.json includes SHA-256 hashes for all files.
If missing, computes SHA-256 and updates the manifest.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "exports" / "capsule_manifest.json"


def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> None:
    if not MANIFEST.exists():
        print(f"⚠️ Manifest not found: {MANIFEST}", file=sys.stderr)
        sys.exit(1)
    
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    
    # Ensure capsule object has sha256
    capsule = data.get("capsule", {})
    capsule_path = ROOT / capsule.get("path", "")
    if capsule_path.exists() and not capsule.get("sha256"):
        sha = compute_sha256(capsule_path)
        capsule["sha256"] = sha
        print(f"✅ Added SHA-256 to capsule: {sha}")
    
    # Ensure all files have sha256
    for fentry in data.get("files", []):
        fpath = ROOT / fentry.get("path", "")
        if fpath.exists() and not fentry.get("sha256"):
            sha = compute_sha256(fpath)
            fentry["sha256"] = sha
            print(f"✅ Added SHA-256 to {fentry['path']}: {sha}")
    
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Capsule manifest updated: {MANIFEST}")


if __name__ == "__main__":
    main()
