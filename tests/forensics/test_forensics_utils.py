"""
Phase XXI - Instruction 113: Error-Logging Tests for Forensics Utilities

Tests for shared forensics utilities:
- Validates utc_now_iso() includes timezone info ("+00:00" or "Z")
- Confirms compute_sha256() returns correct known hash
- Mocks failure in JSON write and ensures log entry is appended
"""
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch, mock_open

# Add root to path for imports
test_dir = Path(__file__).resolve().parent
root_dir = test_dir.parent.parent
sys.path.insert(0, str(root_dir))

from scripts.forensics.forensics_utils import (
    utc_now_iso,
    compute_sha256,
    safe_write_json,
    log_forensics_event
)


def test_utc_now_iso_includes_timezone():
    """Validate that utc_now_iso() returns timezone-aware timestamp."""
    timestamp = utc_now_iso()
    
    # Check that timestamp includes timezone info
    assert '+' in timestamp or 'Z' in timestamp, \
        f'Timestamp must include timezone info: {timestamp}'
    
    # Check that it follows ISO format roughly
    assert 'T' in timestamp, \
        f'Timestamp must be ISO format with T separator: {timestamp}'
    
    # For +00:00 format specifically
    if '+' in timestamp:
        assert '+00:00' in timestamp or timestamp.endswith('+0000'), \
            f'UTC timestamp should have +00:00 timezone: {timestamp}'


def test_compute_sha256_correct_hash():
    """Confirm compute_sha256() returns correct known hash."""
    # Create a test file with known content
    test_file = Path('/tmp/test_forensics_sha256.txt')
    test_content = b'test content for hash verification'
    test_file.write_bytes(test_content)
    
    # Compute hash using our function
    result_hash = compute_sha256(test_file)
    
    # Compute expected hash
    expected_hash = hashlib.sha256(test_content).hexdigest()
    
    assert result_hash == expected_hash, \
        f'Hash mismatch: expected {expected_hash}, got {result_hash}'
    
    # Verify hash is hex string of correct length (64 chars)
    assert len(result_hash) == 64, \
        f'SHA256 hash should be 64 hex characters, got {len(result_hash)}'
    
    # Clean up
    test_file.unlink()


def test_compute_sha256_missing_file():
    """Test that compute_sha256() handles missing files gracefully."""
    nonexistent = Path('/tmp/nonexistent_file_12345.txt')
    
    # Should return empty string for missing file
    result = compute_sha256(nonexistent)
    assert result == '', \
        f'compute_sha256() should return empty string for missing file, got: {result}'


def test_safe_write_json_success(tmp_path):
    """Test successful JSON write with safe_write_json()."""
    test_file = tmp_path / 'test.json'
    test_data = {'key': 'value', 'number': 42, 'list': [1, 2, 3]}
    
    # Write data
    result = safe_write_json(test_file, test_data)
    
    assert result is True, 'safe_write_json() should return True on success'
    assert test_file.exists(), 'File should exist after write'
    
    # Verify content
    loaded_data = json.loads(test_file.read_text(encoding='utf-8'))
    assert loaded_data == test_data, 'Written data should match input data'


def test_safe_write_json_creates_backup(tmp_path):
    """Test that safe_write_json() creates backup of existing file."""
    test_file = tmp_path / 'test.json'
    original_data = {'original': 'data'}
    new_data = {'new': 'data'}
    
    # Write original data
    test_file.write_text(json.dumps(original_data), encoding='utf-8')
    
    # Write new data (should create backup)
    result = safe_write_json(test_file, new_data)
    
    assert result is True, 'safe_write_json() should succeed'
    
    # Check that backup exists
    backup_file = test_file.with_suffix('.json.backup')
    assert backup_file.exists(), 'Backup file should be created'
    
    # Verify backup contains original data
    backup_data = json.loads(backup_file.read_text(encoding='utf-8'))
    assert backup_data == original_data, 'Backup should contain original data'
    
    # Verify main file has new data
    current_data = json.loads(test_file.read_text(encoding='utf-8'))
    assert current_data == new_data, 'Main file should have new data'


def test_safe_write_json_failure_logs_event(tmp_path, monkeypatch):
    """Mock failure in JSON write and ensure log entry is appended."""
    # Set ROOT to tmp_path for this test
    import scripts.forensics.forensics_utils as utils_module
    monkeypatch.setattr(utils_module, 'ROOT', tmp_path)
    
    test_file = tmp_path / 'test.json'
    test_data = {'test': 'data'}
    
    # Mock json.dumps to raise an exception
    def mock_dumps(*args, **kwargs):
        raise ValueError('Mocked JSON serialization error')
    
    with patch('scripts.forensics.forensics_utils.json.dumps', side_effect=mock_dumps):
        result = safe_write_json(test_file, test_data)
        
        assert result is False, 'safe_write_json() should return False on failure'
    
    # Check that error was logged
    log_file = tmp_path / 'forensics_error_log.jsonl'
    assert log_file.exists(), 'Error log should be created'
    
    # Verify log entry
    log_content = log_file.read_text(encoding='utf-8')
    log_entry = json.loads(log_content.strip())
    
    assert log_entry['operation'] == 'safe_write_json', \
        'Log should record operation name'
    assert 'error' in log_entry, 'Log should include error message'
    assert 'timestamp' in log_entry, 'Log should include timestamp'


def test_log_forensics_event_creates_file(tmp_path, monkeypatch):
    """Test that log_forensics_event() creates log file."""
    # Set ROOT to tmp_path for this test
    import scripts.forensics.forensics_utils as utils_module
    monkeypatch.setattr(utils_module, 'ROOT', tmp_path)
    
    event = {'event': 'test_event', 'status': 'success'}
    
    # Log event
    log_forensics_event(event)
    
    # Verify log file exists
    log_file = tmp_path / 'forensics_error_log.jsonl'
    assert log_file.exists(), 'Log file should be created'
    
    # Verify entry
    log_content = log_file.read_text(encoding='utf-8')
    log_entry = json.loads(log_content.strip())
    
    assert log_entry['event'] == 'test_event', 'Event data should be logged'
    assert 'timestamp' in log_entry, 'Timestamp should be added automatically'


def test_log_forensics_event_appends(tmp_path, monkeypatch):
    """Test that log_forensics_event() appends to existing log."""
    # Set ROOT to tmp_path for this test
    import scripts.forensics.forensics_utils as utils_module
    monkeypatch.setattr(utils_module, 'ROOT', tmp_path)
    
    log_file = tmp_path / 'forensics_error_log.jsonl'
    
    # Log first event
    log_forensics_event({'event': 'first'})
    
    # Log second event
    log_forensics_event({'event': 'second'})
    
    # Verify both entries exist
    lines = log_file.read_text(encoding='utf-8').strip().split('\n')
    assert len(lines) == 2, 'Log should contain two entries'
    
    first_entry = json.loads(lines[0])
    second_entry = json.loads(lines[1])
    
    assert first_entry['event'] == 'first', 'First entry should be preserved'
    assert second_entry['event'] == 'second', 'Second entry should be appended'


def test_compute_sha256_large_file(tmp_path):
    """Test compute_sha256() with large file to verify chunked reading."""
    test_file = tmp_path / 'large_file.bin'
    
    # Create a file larger than one chunk (8192 bytes)
    large_content = b'x' * 20000
    test_file.write_bytes(large_content)
    
    # Compute hash
    result_hash = compute_sha256(test_file)
    expected_hash = hashlib.sha256(large_content).hexdigest()
    
    assert result_hash == expected_hash, \
        'Hash should be correct for large files'


if __name__ == '__main__':
    # Simple test runner for manual verification (only tests without fixtures)
    import traceback
    
    tests = [
        test_utc_now_iso_includes_timezone,
        test_compute_sha256_correct_hash,
        test_compute_sha256_missing_file,
    ]
    
    print('Running forensics utilities tests (subset without fixtures)...\n')
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            print(f'✓ {test_func.__name__}')
            passed += 1
        except Exception as e:
            print(f'✗ {test_func.__name__}')
            print(f'  {e}')
            traceback.print_exc()
            failed += 1
    
    print(f'\n{passed} passed, {failed} failed')
    print('\nNote: Full test suite requires pytest for fixture support.')
    sys.exit(0 if failed == 0 else 1)
