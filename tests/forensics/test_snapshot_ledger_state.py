import json
import hashlib
from pathlib import Path
import importlib

mod = importlib.import_module('scripts.forensics.snapshot_ledger_state')


def test_snapshot_creation_hash_and_prune(monkeypatch, tmp_path):
    # Redirect ROOT to temp sandbox
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    artifacts = tmp_path / 'artifacts'
    snapshots = tmp_path / 'snapshots'
    artifacts.mkdir(parents=True, exist_ok=True)

    # Create required ledger files
    (artifacts / 'governance_provenance_ledger.jsonl').write_text('{"id":"e1","msg":"ok"}\n', encoding='utf-8')
    (artifacts / 'governance_ledger_hash.json').write_text('{"sha256":"deadbeef"}', encoding='utf-8')

    # Controlled timestamps to ensure unique filenames
    base = 1_700_000_000  # arbitrary epoch seconds
    def ts_gen():
        n = 0
        while True:
            # Format ISO with seconds, include +00:00
            t = base + n
            import datetime
            dt = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
            yield dt.isoformat()
            n += 1
    g = ts_gen()
    monkeypatch.setattr(mod, 'utc_now_iso', lambda: next(g))

    # Create 11 snapshots
    for _ in range(11):
        rc = mod.main()
        assert rc == 0

    # Only 10 retained
    files = sorted(snapshots.glob('ledger_snapshot_*.tar.gz'))
    assert len(files) == 10

    # Hash record exists and matches computed sha of the latest snapshot
    rec_path = snapshots / 'ledger_snapshot_hash.json'
    data = json.loads(rec_path.read_text(encoding='utf-8'))
    assert isinstance(data, list) and len(data) >= 1
    last = data[-1]
    bundle = snapshots / last['file']
    h = hashlib.sha256()
    with open(bundle, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    assert last['sha256'] == h.hexdigest()

    # Audit marker present
    audit = (tmp_path / 'audit_summary.md').read_text(encoding='utf-8')
    assert 'LEDGER_SNAPSHOT: SAVED' in audit
