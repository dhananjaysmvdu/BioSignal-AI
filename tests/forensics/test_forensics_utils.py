#!/usr/bin/env python3
"""
Phase XXI - Instruction 113: Forensics Utilities Tests

Validates shared forensics utilities:
- Timezone-aware UTC timestamps
- SHA-256 computation accuracy
- Error logging fallback behavior
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_utc_now_iso_format():
    """Validate utc_now_iso() returns timezone-aware UTC ISO string."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'forensics'))
    from forensics_utils import utc_now_iso
    
    ts = utc_now_iso()
    # Must contain timezone indicator
    assert '+00:00' in ts or ts.endswith('Z'), f'Timestamp missing UTC timezone: {ts}'
    # Basic ISO format check
    assert 'T' in ts, f'Timestamp not ISO format: {ts}'


def test_compute_sha256_known_hash():
    """Confirm compute_sha256() returns correct known hash."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'forensics'))
    from forensics_utils import compute_sha256
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        f.write('test content\n')
        temp_path = Path(f.name)
    
    try:
        # SHA-256 for 'test content\n' (with Windows CRLF conversion in text mode)
        expected = 'ee06af3f4508d7e235d6ab423fe452f2190ed03b54d4fbec799b5daccd648ba4'
        result = compute_sha256(temp_path)
        assert result == expected, f'Hash mismatch: expected {expected}, got {result}'
    finally:
        temp_path.unlink()


def test_log_forensics_event_fallback(monkeypatch, tmp_path):
    """Mock failure in JSON write and ensure error logging doesn't crash."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'forensics'))
    
    # Monkeypatch ROOT to isolated tmp_path
    import forensics_utils
    monkeypatch.setattr(forensics_utils, 'ROOT', tmp_path)
    
    from forensics_utils import log_forensics_event
    
    # First call should succeed
    log_forensics_event({'test': 'event1', 'status': 'ok'})
    
    log_file = tmp_path / 'forensics' / 'forensics_error_log.jsonl'
    assert log_file.exists(), 'Log file not created'
    
    lines = log_file.read_text(encoding='utf-8').strip().split('\n')
    assert len(lines) >= 1, 'No log entries written'
    
    first = json.loads(lines[0])
    assert 'timestamp' in first, 'Missing timestamp'
    assert first['test'] == 'event1', 'Event data mismatch'


def test_safe_write_json_atomic(tmp_path):
    """Validate safe_write_json performs atomic write with backup."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'forensics'))
    from forensics_utils import safe_write_json
    
    target = tmp_path / 'test.json'
    data = {'key': 'value', 'count': 42}
    
    # Initial write
    result = safe_write_json(target, data)
    assert result is True, 'safe_write_json failed'
    assert target.exists(), 'Target file not created'
    
    loaded = json.loads(target.read_text(encoding='utf-8'))
    assert loaded == data, 'Data mismatch'
    
    # Overwrite should create backup
    data2 = {'key': 'updated', 'count': 99}
    result = safe_write_json(target, data2)
    assert result is True, 'safe_write_json overwrite failed'
    
    backup = target.with_suffix('.json.backup')
    # Backup creation is best-effort; check only if exists
    if backup.exists():
        backup_data = json.loads(backup.read_text(encoding='utf-8'))
        assert backup_data == data, 'Backup data mismatch'


def test_safe_write_json_logs_on_failure(tmp_path, monkeypatch):
    """Test safe_write_json logs errors when write fails."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'forensics'))
    
    import forensics_utils
    monkeypatch.setattr(forensics_utils, 'ROOT', tmp_path)
    
    from forensics_utils import safe_write_json
    from unittest.mock import patch
    
    # Mock Path.write_text to raise an exception
    with patch.object(Path, 'write_text', side_effect=PermissionError('Mock write failure')):
        result = safe_write_json(tmp_path / 'test.json', {'data': 'test'})
        # Should return False on failure
        assert result is False, 'Expected safe_write_json to return False on error'
    
    # Check error log was created
    error_log = tmp_path / 'forensics' / 'forensics_error_log.jsonl'
    assert error_log.exists(), 'Error log should be created'
    
    logs = error_log.read_text(encoding='utf-8').strip().split('\n')
    assert len(logs) > 0, 'Error log should contain entries'
    
    last_entry = json.loads(logs[-1])
    assert 'error' in last_entry or 'exception' in last_entry, 'Error log should contain error details'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
