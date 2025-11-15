#!/usr/bin/env python3
"""
Phase XIX - Instruction 103: Consensus Trust Bridge

Combines provenance consensus and trust federation report into a unified
trust_consensus_report.json and appends an audit marker.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FED = ROOT / 'federation'
RESULTS = ROOT / 'results'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_marker(ts: str) -> None:
    audit = ROOT / 'audit_summary.md'
    with audit.open('a', encoding='utf-8') as f:
        f.write(f'<!-- TRUST_CONSENSUS: UPDATED {ts} -->\n')


def main() -> int:
    prov = FED / 'provenance_consensus.json'
    trust = RESULTS / 'trust_federation_report.json'
    prov_j = json.loads(prov.read_text(encoding='utf-8')) if prov.exists() else {}
    trust_j = json.loads(trust.read_text(encoding='utf-8')) if trust.exists() else {}

    out = {
        'timestamp': utc_now_iso(),
        'provenance': {
            'agreement_pct': prov_j.get('agreement_pct'),
            'ledger_agreement_pct': prov_j.get('ledger_agreement_pct'),
            'anchor_agreement_pct': prov_j.get('anchor_agreement_pct'),
            'bundle_agreement_pct': prov_j.get('bundle_agreement_pct'),
        },
        'trust': {
            'status': trust_j.get('status'),
            'peers_checked': trust_j.get('peers_checked'),
            'agreement_pct': trust_j.get('agreement_pct') or (100.0 if trust_j.get('status') == 'verified' else 0.0),
        }
    }
    FED.mkdir(parents=True, exist_ok=True)
    (FED / 'trust_consensus_report.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    append_marker(out['timestamp'])
    print(json.dumps(out, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
