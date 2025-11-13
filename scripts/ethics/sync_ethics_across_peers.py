"""Cross-Federation Ethics Synchronization (Phase XII Instruction 66)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PEERS = ROOT/"federation"/"peers.json"
POLICY = ROOT/"config"/"certification_policy.json"
LOG = ROOT/"ethics"/"ethics_sync_log.jsonl"
TRANSP = ROOT/"GOVERNANCE_TRANSPARENCY.md"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def append_log(entry: dict):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as fh:
        import json
        fh.write(json.dumps(entry) + '\n')


def main():
    policy = load(POLICY)
    fairness_min = float(policy.get('fairness_min_pct', 98.0))
    updated = False
    if fairness_min < 98.0:
        policy['fairness_min_pct'] = 98.0
        updated = True
    if updated:
        POLICY.parent.mkdir(parents=True, exist_ok=True)
        POLICY.write_text(json.dumps(policy, indent=2), encoding='utf-8')
    append_log({
        'timestamp': utc_iso(),
        'event': 'ethics_sync',
        'fairness_min_pct': policy.get('fairness_min_pct', 98.0),
        'policy_updated': updated
    })
    # Append marker to transparency doc
    if TRANSP.exists():
        with TRANSP.open('a', encoding='utf-8') as fh:
            fh.write(f"\n<!-- ETHICS_SYNC: UPDATED {utc_iso()} -->\n")
    print(json.dumps({'updated': updated}))


if __name__ == '__main__':
    main()
