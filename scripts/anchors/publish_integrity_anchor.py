"""Integrity Anchor Publisher (Phase XIII Instruction 73).

Computes a combined SHA-256 integrity anchor from key governance artifacts and
publishes it to external verifiable ledgers when credentials are present.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "governance_provenance_ledger.jsonl"
META_FEED = ROOT / "portal" / "meta_audit_feed.json"
FED_STATUS = ROOT / "federation" / "federation_status.json"
OUT = ROOT / "integrity_anchor.json"
LOG = ROOT / "anchors" / "anchor_log.jsonl"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_path(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def combined_hash(components: Dict[str, str | None]) -> str:
    h = hashlib.sha256()
    for k in sorted(components.keys()):
        v = components[k] or ''
        h.update(k.encode('utf-8') + b'=' + v.encode('utf-8') + b'\n')
    return h.hexdigest()


def log_event(event: str, meta: Dict[str, object]):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": utc_iso(), "event": event, "metadata": meta}
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(payload) + "\n")


def publish_gist(content: str) -> str | None:
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        return None
    data = json.dumps({
        "description": "BioSignal-AI Integrity Anchor",
        "public": True,
        "files": {"integrity_anchor.json": {"content": content}}
    }).encode('utf-8')
    req = urllib.request.Request('https://api.github.com/gists', data=data, method='POST')
    req.add_header('Authorization', f'token {token}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec - controlled API call
        body = json.loads(resp.read().decode('utf-8'))
        return body.get('html_url') or body.get('url')


def publish_zenodo_metadata(anchor: dict) -> str | None:
    # Placeholder: require environment ZENODO_TOKEN and ZENODO_DEPOSITION_ID
    token = os.environ.get('ZENODO_TOKEN')
    deposition_id = os.environ.get('ZENODO_DEPOSITION_ID')
    if not token or not deposition_id:
        return None
    # Minimal metadata patch (concept DOI alignment)
    url = f'https://zenodo.org/api/deposit/depositions/{deposition_id}'
    req = urllib.request.Request(url, method='PUT')
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    data = json.dumps({
        'metadata': {
            'notes': f"Updated with integrity anchor {anchor.get('combined_sha256')} at {anchor.get('timestamp')}"
        }
    }).encode('utf-8')
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:  # nosec - controlled API call
            body = json.loads(resp.read().decode('utf-8'))
            return str(body.get('id'))
    except Exception:
        return None


def main() -> int:
    components = {
        'governance_provenance_ledger.jsonl': sha256_path(LEDGER),
        'portal/meta_audit_feed.json': sha256_path(META_FEED),
        'federation/federation_status.json': sha256_path(FED_STATUS),
    }
    combo = combined_hash(components)
    anchor = {
        'timestamp': utc_iso(),
        'components': components,
        'combined_sha256': combo,
    }
    OUT.write_text(json.dumps(anchor, indent=2), encoding='utf-8')
    log_event('integrity_anchor_computed', {'combined_sha256': combo})

    # Publish to gist if token present
    gist_url = None
    try:
        gist_url = publish_gist(json.dumps(anchor, indent=2))
        if gist_url:
            log_event('gist_published', {'url': gist_url})
    except Exception as exc:
        log_event('gist_publish_error', {'error': str(exc)})

    # Optionally update Zenodo metadata
    try:
        zenodo_id = publish_zenodo_metadata(anchor)
        if zenodo_id:
            log_event('zenodo_metadata_updated', {'deposition_id': zenodo_id})
    except Exception as exc:
        log_event('zenodo_publish_error', {'error': str(exc)})

    print(json.dumps({'status': 'ok', 'combined_sha256': combo, 'gist': gist_url}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
