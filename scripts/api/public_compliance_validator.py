"""Public Compliance Validator (Phase XIV Instruction 79).

Validates ledger integrity and DOI/certification linkage, emits portal/public_compliance_status.json
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / 'governance_provenance_ledger.jsonl'
LEDGER_HASH = ROOT / 'governance_ledger_hash.json'
README = ROOT / 'README.md'
TRANSPARENCY = ROOT / 'GOVERNANCE_TRANSPARENCY.md'
OUT = ROOT / 'portal' / 'public_compliance_status.json'


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


def load_ledger() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not LEDGER.exists():
        return entries
    for line in LEDGER.read_text(encoding='utf-8').splitlines():
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return entries


def has_utc(ts: str | None) -> bool:
    if not ts:
        return False
    return ts.endswith('Z') or ts.endswith('+00:00') or ts.endswith('+00') or ('+0' in ts)


def main() -> int:
    issues: List[str] = []
    # Integrity hash match
    computed = sha256_path(LEDGER)
    reported = None
    entries = load_ledger()
    if LEDGER_HASH.exists():
        try:
            j = json.loads(LEDGER_HASH.read_text(encoding='utf-8'))
            reported = j.get('sha256')
        except Exception:
            reported = None
    if not computed or not reported or computed != reported:
        issues.append('ledger_hash_mismatch')

    # UTC timestamp presence for each entry
    for e in entries:
        if not has_utc(e.get('timestamp')):
            issues.append('missing_utc_timestamp')
            break

    # DOI and certification linkage
    doi_present = False
    try:
        text = ''
        if README.exists():
            text += README.read_text(encoding='utf-8')
        if TRANSPARENCY.exists():
            text += TRANSPARENCY.read_text(encoding='utf-8')
        if re.search(r'10\.5281/zenodo\.\d+', text):
            doi_present = True
    except Exception:
        pass

    if not doi_present:
        issues.append('missing_doi_reference')

    cert_ok = any((e.get('certification') or '').strip() for e in entries)
    if not cert_ok:
        issues.append('missing_certification')

    ok = len(issues) == 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        'timestamp': utc_iso(),
        'compliance': ok,
        'issues': issues,
    }, indent=2), encoding='utf-8')
    print(json.dumps({'compliance': ok, 'issues': issues}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
