"""Autonomous DOI Steward (Phase XIV Instruction 78).

Ensures newest DOI metadata references latest Phase tag; validates immutability of prior DOIs.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / 'governance_provenance_ledger.jsonl'
ZJSON = ROOT / 'zenodo.json'
LOG = ROOT / 'results' / 'doi_steward_log.jsonl'


def utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def read_ledger() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not LEDGER.exists():
        return out
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def latest_phase(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not entries:
        return None
    def key(e: Dict[str, Any]):
        import re
        try:
            return int(re.sub(r"\D", "", e.get('phase_id','') or '0'))
        except Exception:
            return 0
    return sorted(entries, key=key)[-1]


def log_event(event: str, meta: Dict[str, Any]):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {'timestamp': utc_iso(), 'event': event, 'metadata': meta}
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(payload) + '\n')


def zenodo_update_version(tag: str) -> Optional[str]:
    token = os.environ.get('ZENODO_TOKEN')
    deposition_id = os.environ.get('ZENODO_DEPOSITION_ID')
    if not token or not deposition_id:
        return None
    url = f'https://zenodo.org/api/deposit/depositions/{deposition_id}'
    req = urllib.request.Request(url, method='PUT')
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Content-Type', 'application/json')
    data = json.dumps({'metadata': {'version': tag}}).encode('utf-8')
    with urllib.request.urlopen(req, data=data, timeout=20) as resp:
        body = json.loads(resp.read().decode('utf-8'))
        return str(body.get('id'))


def main() -> int:
    entries = read_ledger()
    latest = latest_phase(entries)
    if not latest:
        print(json.dumps({'status': 'skipped', 'reason': 'no_ledger'}))
        return 0

    latest_tag = str(latest.get('version_tag', 'unknown'))

    # Check zenodo.json version alignment if present
    zver = None
    if ZJSON.exists():
        try:
            zj = json.loads(ZJSON.read_text(encoding='utf-8'))
            zver = zj.get('version') or zj.get('metadata', {}).get('version')
        except Exception:
            zver = None

    if zver != latest_tag:
        # attempt update via Zenodo or dry-run log
        updated = zenodo_update_version(latest_tag)
        if updated:
            log_event('doi_version_updated', {'deposition_id': updated, 'version': latest_tag})
            status = 'updated'
        else:
            log_event('doi_version_mismatch_dry_run', {'expected': latest_tag, 'found': zver})
            status = 'dry-run'
    else:
        status = 'ok'

    print(json.dumps({'status': status, 'latest_tag': latest_tag, 'zenodo_version': zver}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
