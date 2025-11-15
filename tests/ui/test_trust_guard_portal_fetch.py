from __future__ import annotations

from pathlib import Path


def test_portal_files_exist():
    root = Path(__file__).resolve().parents[2]
    override = root / 'portal' / 'override.html'
    index = root / 'portal' / 'index.html'
    trust = root / 'portal' / 'trust_guard.html'
    assert override.exists() and index.exists() and trust.exists()


def test_js_paths_are_relative():
    root = Path(__file__).resolve().parents[2]
    trust = (root / 'portal' / 'trust_guard.html').read_text(encoding='utf-8')
    assert "fetch('/trust/status'" in trust
    assert "fetch('/trust/force-unlock'" in trust
    for bad in ['http://', 'https://', 'file://']:
        assert bad not in trust
