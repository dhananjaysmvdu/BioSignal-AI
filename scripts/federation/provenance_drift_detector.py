#!/usr/bin/env python3
"""
Phase XIX - Instruction 102: Cross-Node Drift Detector

Reads federation/provenance_consensus.json and logs drift if agreement < 100%.
Option --repair: rebuild documentation bundle and re-run sync engine.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FED = ROOT / 'federation'


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_line(p: Path, line: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a', encoding='utf-8') as f:
        f.write(line.rstrip() + "\n")


def append_audit_marker(ts: str) -> None:
    audit = ROOT / 'audit_summary.md'
    with audit.open('a', encoding='utf-8') as f:
        f.write(f'<!-- PROVENANCE_DRIFT: DETECTED {ts} -->\n')


def load_consensus() -> dict:
    p = FED / 'provenance_consensus.json'
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding='utf-8'))


def repair():
    # Rebuild bundle and rerun sync; ignore failures for safety
    try:
        subprocess.run(['python', 'scripts/docs/build_doc_provenance_bundle.py'], cwd=str(ROOT), timeout=300)
    except Exception:
        pass
    try:
        subprocess.run(['python', 'scripts/federation/provenance_sync_engine.py'], cwd=str(ROOT), timeout=300)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repair', action='store_true')
    args = ap.parse_args()

    c = load_consensus()
    if not c:
        print('No consensus file found')
        return 0

    pct = float(c.get('agreement_pct', 0))
    if pct < 100.0:
        ts = utc_now_iso()
        append_line(FED / 'provenance_drift_log.jsonl', json.dumps({'timestamp': ts, 'agreement_pct': pct, 'consensus': c}))
        append_audit_marker(ts)
        if args.repair:
            repair()
        # Fail if drift > 10%
        if pct < 90.0:
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
