"""Publish archival bundle and align DOI (Phase XIII Instruction 74).

Creates exports/reflex_governance_archive_v1.6.zip with key provenance files and
optionally updates a Zenodo deposition. On success, updates README.md and
GOVERNANCE_TRANSPARENCY.md with the minted DOI.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "exports"
ZIPNAME = EXPORTS / "reflex_governance_archive_v1.6.zip"

PHASE_REPORTS = sorted(ROOT.glob("PHASE_*_COMPLETION_REPORT.md"))
INCLUDE_FILES = [
    ROOT / "governance_provenance_ledger.jsonl",
    ROOT / "integrity_anchor.json",
    ROOT / "portal" / "meta_audit_feed.json",
    ROOT / "portal" / "ledger.html",
]

README = ROOT / "README.md"
TRANSPARENCY = ROOT / "GOVERNANCE_TRANSPARENCY.md"


def utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def build_zip() -> Path:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIPNAME, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for p in PHASE_REPORTS:
            if p.exists():
                zf.write(p, arcname=p.name)
        for p in INCLUDE_FILES:
            if p.exists():
                zf.write(p, arcname=str(p.relative_to(ROOT)))
        # manifest
        manifest = {
            'timestamp': utc_iso(),
            'files': [p.name for p in PHASE_REPORTS] + [str(p.relative_to(ROOT)) for p in INCLUDE_FILES],
        }
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
    return ZIPNAME


def zenodo_upload(zip_path: Path, *, dry_run: bool = False, timeouts: Optional[dict] = None) -> Optional[str]:
    """Upload archive to Zenodo and publish, returning DOI or None.

    Hardened with timeouts and graceful fallbacks. Set dry_run=True to skip network.
    Timeouts can be overridden via dict keys: meta, upload, publish (seconds).
    """
    if timeouts is None:
        timeouts = {}
    to_meta = float(timeouts.get('meta', os.environ.get('ZENODO_TIMEOUT_META', 20)))
    to_upload = float(timeouts.get('upload', os.environ.get('ZENODO_TIMEOUT_UPLOAD', 60)))
    to_publish = float(timeouts.get('publish', os.environ.get('ZENODO_TIMEOUT_PUBLISH', 20)))

    if dry_run or os.environ.get('ZENODO_DRY_RUN') == '1':
        return None

    token = os.environ.get('ZENODO_TOKEN')
    deposition_id = os.environ.get('ZENODO_DEPOSITION_ID')
    if not token or not deposition_id:
        return None
    try:
        # Upload file to deposition bucket
        bucket_url = os.environ.get('ZENODO_BUCKET_URL')
        if not bucket_url:
            # Try to fetch deposition to obtain bucket
            req = urllib.request.Request(f'https://zenodo.org/api/deposit/depositions/{deposition_id}')
            req.add_header('Authorization', f'Bearer {token}')
            with urllib.request.urlopen(req, timeout=to_meta) as resp:
                info = json.loads(resp.read().decode('utf-8'))
                bucket_url = info['links']['bucket']

        # PUT file (read into memory; archive is relatively small). Add headers.
        put = urllib.request.Request(f"{bucket_url}/{zip_path.name}", method='PUT')
        put.add_header('Authorization', f'Bearer {token}')
        put.add_header('Content-Type', 'application/zip')
        size = zip_path.stat().st_size
        put.add_header('Content-Length', str(size))
        with zip_path.open('rb') as fh:
            data = fh.read()
        with urllib.request.urlopen(put, data=data, timeout=to_upload) as up:
            _ = up.read()

        # Publish deposition
        req = urllib.request.Request(
            f'https://zenodo.org/api/deposit/depositions/{deposition_id}/actions/publish', method='POST'
        )
        req.add_header('Authorization', f'Bearer {token}')
        with urllib.request.urlopen(req, data=b'', timeout=to_publish) as pub:
            rec = json.loads(pub.read().decode('utf-8'))
            doi = rec.get('doi') or rec.get('metadata', {}).get('doi')
            return doi
    except Exception as e:
        # Graceful fallback on any network or API error
        print(json.dumps({'status': 'zenodo_error', 'error': str(e)}))
        return None


def update_doi_in_file(path: Path, new_doi: str) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding='utf-8')
    # Replace an existing Zenodo DOI or append if missing
    if re.search(r"10\.5281/zenodo\.\d+", text):
        text = re.sub(r"10\.5281/zenodo\.\d+", new_doi, text)
    else:
        text += f"\n\nUpdated DOI: {new_doi}\n"
    path.write_text(text, encoding='utf-8')


def main() -> int:
    # Simple CLI flags via env or argv for CI convenience
    dry_run = ('--dry-run' in sys.argv) or (os.environ.get('ARCHIVE_DRY_RUN') == '1')
    skip_zenodo = ('--skip-zenodo' in sys.argv) or (os.environ.get('SKIP_ZENODO') == '1')

    zip_path = build_zip()
    doi = None if skip_zenodo else zenodo_upload(zip_path, dry_run=dry_run)
    if doi:
        update_doi_in_file(README, doi)
        update_doi_in_file(TRANSPARENCY, doi)
        print(json.dumps({'status': 'ok', 'zip': str(zip_path), 'doi': doi}))
    else:
        print(json.dumps({'status': 'skipped', 'zip': str(zip_path), 'doi': None}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
