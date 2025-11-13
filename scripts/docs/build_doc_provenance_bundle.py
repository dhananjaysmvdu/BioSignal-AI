#!/usr/bin/env python3
"""
Phase XV - Instruction 83

Build Documentation Provenance Bundle:
- Collect integrity JSONs and reports
- Compress to exports/documentation_provenance_bundle.zip
- Record bundle hash to docs/documentation_provenance_hash.json
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
EXPORTS = ROOT / 'exports'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def collect_files() -> list[Path]:
    files = []
    # Required if exist
    for rel in [
        'docs/readme_integrity.json',
        'docs/transparency_integrity.json',
        'INSTRUCTION_EXECUTION_SUMMARY.md',
    ]:
        p = ROOT / rel
        if p.exists():
            files.append(p)

    # Latest PHASE_*_COMPLETION_REPORT.md (by mtime)
    phase_candidates = list(ROOT.glob('PHASE_*_COMPLETION_REPORT.md'))
    if phase_candidates:
        latest = max(phase_candidates, key=lambda x: x.stat().st_mtime)
        files.append(latest)
    return files


def build_bundle() -> Path:
    files = collect_files()
    EXPORTS.mkdir(parents=True, exist_ok=True)
    bundle = EXPORTS / 'documentation_provenance_bundle.zip'
    with ZipFile(bundle, 'w', ZIP_DEFLATED) as z:
        for fp in files:
            arcname = fp.relative_to(ROOT).as_posix()
            z.write(fp, arcname)
    return bundle


def write_hash(bundle: Path) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / 'documentation_provenance_hash.json'
    out.write_text(
        json.dumps({'timestamp': utc_now_iso(), 'sha256': sha256_path(bundle)}, indent=2),
        encoding='utf-8'
    )


def main() -> None:
    bundle = build_bundle()
    write_hash(bundle)
    print(f'Wrote bundle to {bundle}')


if __name__ == '__main__':
    main()
