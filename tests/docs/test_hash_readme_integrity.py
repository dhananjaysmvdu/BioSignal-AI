import json
import hashlib
import os
from pathlib import Path
import importlib
import types

SCRIPT = 'scripts.docs.hash_readme_integrity'
mod = importlib.import_module(SCRIPT)
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'


def test_sha256_matches_hashlib(tmp_path):
    p = tmp_path / 'sample.txt'
    content = b'hello-world-123\n'
    p.write_bytes(content)

    got = mod.sha256_path(p)
    exp = hashlib.sha256(content).hexdigest()
    assert got == exp


def test_readme_timestamp_is_utc_and_json_written(monkeypatch):
    # Ensure a clean write
    if (DOCS / 'readme_integrity.json').exists():
        (DOCS / 'readme_integrity.json').unlink()

    # Monkeypatch commit messages to include docs to avoid failure if README changed
    monkeypatch.setattr(mod, 'get_recent_commit_messages', lambda n=30: ['docs: touch readme'])

    rc = mod.main()
    assert rc == 0

    data = json.loads((DOCS / 'readme_integrity.json').read_text(encoding='utf-8'))
    ts = data['timestamp']
    # ISO-8601 UTC must include +00:00 (or Z, but our script uses +00:00)
    assert ts.endswith('+00:00') or ts.endswith('Z')
    assert len(data['sha256']) == 64


def test_failure_on_readme_change_without_docs_commit(monkeypatch, tmp_path):
    # Prepare previous hash different from current README hash
    readme = ROOT / 'README.md'
    cur_sha = mod.sha256_path(readme)
    prev_sha = '0' * 64 if cur_sha != ('0' * 64) else 'f' * 64
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / 'readme_integrity.json').write_text(
        json.dumps({'timestamp': '2025-01-01T00:00:00+00:00', 'sha256': prev_sha}),
        encoding='utf-8'
    )

    # No docs/readme mention in recent commits
    monkeypatch.setattr(mod, 'get_recent_commit_messages', lambda n=30: ['feat: update model', 'refactor: cleanup'])

    rc = mod.main()
    assert rc == 1
