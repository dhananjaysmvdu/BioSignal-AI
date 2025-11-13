import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib

SCRIPT = 'scripts.docs.hash_readme_integrity'
mod = importlib.import_module(SCRIPT)
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'


def _write_prev_transparency(ts: datetime, sha: str = 'aaa'):
    payload = {
        'GOVERNANCE_TRANSPARENCY.md': {'timestamp': ts.isoformat(), 'sha256': sha},
        'INSTRUCTION_EXECUTION_SUMMARY.md': {'timestamp': ts.isoformat(), 'sha256': sha},
        'docs/audit_summary.md': {'timestamp': ts.isoformat(), 'sha256': sha},
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / 'transparency_integrity.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')


def _count_drift_markers():
    f = DOCS / 'audit_summary.md'
    if not f.exists():
        return 0
    return f.read_text(encoding='utf-8').count('TRANSPARENCY_DRIFT: DETECTED')


def test_drift_marker_added_for_old_timestamp():
    # Set previous timestamp to > 2 days ago
    old_ts = datetime.now(timezone.utc) - timedelta(days=3)
    _write_prev_transparency(old_ts, sha='old123')

    before = _count_drift_markers()
    mod.verify_transparency()
    after = _count_drift_markers()
    assert after == before + 1


def test_no_marker_for_recent_timestamp():
    recent_ts = datetime.now(timezone.utc) - timedelta(days=1)
    _write_prev_transparency(recent_ts, sha='old456')

    before = _count_drift_markers()
    mod.verify_transparency()
    after = _count_drift_markers()
    # No new marker should be added
    assert after == before
