import json
import sys
import subprocess
from pathlib import Path

SCRIPT = Path('scripts/workflow_utils/schema_provenance_ledger.py')


def run_ledger(ledger: Path, audit: Path) -> int:
    cmd = [sys.executable, str(SCRIPT), '--ledger', str(ledger), '--audit-summary', str(audit)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    return res.returncode


def read_jsonl(path: Path):
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    return entries


def test_schema_ledger_idempotent(tmp_path: Path):
    ledger = tmp_path / 'schema_provenance_ledger.jsonl'
    audit = tmp_path / 'audit_summary.md'

    rc1 = run_ledger(ledger, audit)
    assert rc1 == 0
    entries1 = read_jsonl(ledger)
    assert len(entries1) == 1
    first_hash = entries1[0]['schema_hash']

    rc2 = run_ledger(ledger, audit)
    assert rc2 == 0
    entries2 = read_jsonl(ledger)
    assert len(entries2) == 1  # unchanged
    assert entries2[0]['schema_hash'] == first_hash

    audit_text = audit.read_text(encoding='utf-8')
    assert '<!-- SCHEMA_PROVENANCE:BEGIN -->' in audit_text
