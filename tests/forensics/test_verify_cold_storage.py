import json
import hashlib
from pathlib import Path
import importlib
import tarfile

mod = importlib.import_module('scripts.forensics.verify_cold_storage')


def test_cold_storage_verification_logs_and_markers(monkeypatch, tmp_path):
    # Redirect ROOT
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    snapshots = tmp_path / 'snapshots'
    mirrors = tmp_path / 'mirrors'
    forensics = tmp_path / 'forensics'
    snapshots.mkdir(parents=True, exist_ok=True)
    mirrors.mkdir(parents=True, exist_ok=True)

    # Create dummy snapshot bundle and record
    bundle = snapshots / 'ledger_snapshot_20250101T000000Z.tar.gz'
    with tarfile.open(bundle, 'w:gz') as z:
        # add a trivial file
        f = tmp_path / 'dummy.txt'
        f.write_text('x', encoding='utf-8')
        z.add(f, arcname='dummy.txt')
    h = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (snapshots / 'ledger_snapshot_hash.json').write_text(json.dumps([{'timestamp':'2025-01-01T00:00:00+00:00','file':bundle.name,'sha256':h}], indent=2), encoding='utf-8')

    # Create mirror and chain with continuity
    a1 = mirrors / 'anchor_20250101T000000Z.json'
    a1.write_text('{"x":1}', encoding='utf-8')
    s1 = hashlib.sha256(a1.read_bytes()).hexdigest()
    c1 = hashlib.sha256(('' + s1).encode('utf-8')).hexdigest()
    a2 = mirrors / 'anchor_20250101T000100Z.json'
    a2.write_text('{"x":2}', encoding='utf-8')
    s2 = hashlib.sha256(a2.read_bytes()).hexdigest()
    c2 = hashlib.sha256((c1 + s2).encode('utf-8')).hexdigest()
    (mirrors / 'anchor_chain.json').write_text(json.dumps([
        {'timestamp':'2025-01-01T00:00:00+00:00','file':a1.name,'sha256':s1,'chain_hash':c1},
        {'timestamp':'2025-01-01T00:01:00+00:00','file':a2.name,'sha256':s2,'chain_hash':c2},
    ], indent=2), encoding='utf-8')

    # Run verify
    rc = mod.main()
    assert rc == 0

    # Log appended and entries verified
    log = (forensics / 'verification_log.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert len(log) >= 3
    for line in log:
        data = json.loads(line)
        assert data.get('verified') is True

    # Audit marker present
    audit = (tmp_path / 'audit_summary.md').read_text(encoding='utf-8')
    assert 'COLD_STORAGE_VERIFY: UPDATED' in audit
