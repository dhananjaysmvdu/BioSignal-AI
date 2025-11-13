"""Federated Trust Exchange (Phase XIV Instruction 77).

Collects peer trust artifacts, validates cross-ledger integrity and time sync, and emits a report.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
PEERS = ROOT / 'federation' / 'peers.json'
REPORT = ROOT / 'results' / 'trust_federation_report.json'
LOG = ROOT / 'results' / 'trust_federation_log.jsonl'
AUDIT = ROOT / 'audit_summary.md'


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Dict[str, Any] | List[Any] | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def fetch_peer_json(base: str, rel: str) -> Dict[str, Any] | None:
    # Support http(s) and local relative paths
    import urllib.request
    if base.startswith('http://') or base.startswith('https://'):
        try:
            with urllib.request.urlopen(base.rstrip('/') + '/' + rel, timeout=10) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return None
    p = (ROOT / Path(base) / rel).resolve()
    return read_json(p)


def log_event(event: str, meta: Dict[str, Any]):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": utc_iso(), "event": event, "metadata": meta}
    with LOG.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(payload) + '\n')


def validate_peer(base: str, name: str, tolerance_sec: int = 60) -> Dict[str, Any]:
    ledger_hash = fetch_peer_json(base, 'governance_ledger_hash.json')
    anchor = fetch_peer_json(base, 'integrity_anchor.json')
    issues: List[str] = []
    ok = True

    ledger_sha = None
    ledger_ts = None
    if isinstance(ledger_hash, dict):
        ledger_sha = ledger_hash.get('sha256')
        ledger_ts = ledger_hash.get('timestamp')
        if not ledger_sha:
            ok = False
            issues.append('missing_ledger_sha')
    else:
        ok = False
        issues.append('missing_ledger_hash')

    anchor_combo = None
    anchor_comp_sha = None
    anchor_ts = None
    if isinstance(anchor, dict):
        anchor_combo = anchor.get('combined_sha256')
        comps = anchor.get('components') or {}
        anchor_comp_sha = comps.get('governance_provenance_ledger.jsonl')
        anchor_ts = anchor.get('timestamp')
    else:
        issues.append('missing_integrity_anchor')

    if ledger_sha and anchor_comp_sha and ledger_sha != anchor_comp_sha:
        ok = False
        issues.append('ledger_anchor_mismatch')

    # Timestamp tolerance check
    def to_dt(s: str | None):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00'))
        except Exception:
            return None

    lt = to_dt(ledger_ts)
    at = to_dt(anchor_ts)
    if lt and at:
        delta = abs((lt - at).total_seconds())
        if delta > tolerance_sec:
            ok = False
            issues.append('timestamp_drift')

    return {
        'peer': name,
        'base': base,
        'ok': ok,
        'issues': issues,
        'ledger_sha256': ledger_sha,
        'anchor_ledger_component_sha256': anchor_comp_sha,
        'ledger_timestamp': ledger_ts,
        'anchor_timestamp': anchor_ts,
    }


def main() -> int:
    peers = read_json(PEERS)
    if not isinstance(peers, list):
        peers = []
    results: List[Dict[str, Any]] = []
    for peer in peers:
        base = str(peer.get('base', '')).strip()
        name = str(peer.get('name', base or 'peer'))
        if not base:
            continue
        res = validate_peer(base, name)
        results.append(res)
        if not res['ok']:
            log_event('trust_drift', {'peer': name, 'issues': res['issues']})

    overall = all(r.get('ok') for r in results) if results else True
    status = 'verified' if overall else 'drift'

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({'timestamp': utc_iso(), 'status': status, 'peers': results}, indent=2), encoding='utf-8')

    # Append audit marker
    if AUDIT.exists():
        with AUDIT.open('a', encoding='utf-8') as fh:
            fh.write(f"<!-- TRUST_FEDERATION: UPDATED {utc_iso()} -->\n")

    print(json.dumps({'status': status, 'peers_checked': len(results)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
