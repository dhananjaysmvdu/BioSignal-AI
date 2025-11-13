import json
import hashlib
from pathlib import Path
import importlib

mod = importlib.import_module('scripts.forensics.mirror_integrity_anchor')


def test_anchor_chain_continuity(monkeypatch, tmp_path):
    # Redirect ROOT to temp
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    artifacts = tmp_path / 'artifacts'
    mirrors = tmp_path / 'mirrors'
    artifacts.mkdir(parents=True, exist_ok=True)

    # Minimal anchor content
    (artifacts / 'integrity_anchor.json').write_text('{"combined_sha256":"abc123"}', encoding='utf-8')

    # Two distinct timestamps
    times = ['2025-01-01T00:00:00+00:00', '2025-01-01T00:00:01+00:00']
    it = iter(times)
    monkeypatch.setattr(mod, 'utc_now_iso', lambda: next(it))

    # First mirror
    rc1 = mod.main()
    assert rc1 == 0
    # Second mirror
    rc2 = mod.main()
    assert rc2 == 0

    chain = json.loads((mirrors / 'anchor_chain.json').read_text(encoding='utf-8'))
    assert len(chain) >= 2

    # Recompute chain continuity
    prev_chain_hash = ''
    for entry in chain:
        f = mirrors / entry['file']
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        assert sha == entry['sha256']
        exp_chain = hashlib.sha256((prev_chain_hash + entry['sha256']).encode('utf-8')).hexdigest()
        assert exp_chain == entry['chain_hash']
        prev_chain_hash = entry['chain_hash']

    # Audit marker present
    audit = (tmp_path / 'audit_summary.md').read_text(encoding='utf-8')
    assert 'ANCHOR_MIRROR: VERIFIED' in audit
