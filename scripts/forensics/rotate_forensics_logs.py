#!/usr/bin/env python3
"""
Phase XXI - Instruction 112: Forensics Log Rotation & Compression

Rotates forensics_error_log.jsonl when it exceeds 10 MB or 1000 lines:
- Compresses to forensics_error_log_<UTC ISO>.gz
- Truncates original and inserts baseline entry
- Appends audit marker to audit_summary.md
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.forensics.forensics_utils import utc_now_iso

LOG_FILE = ROOT / 'forensics_error_log.jsonl'
AUDIT_FILE = ROOT / 'audit_summary.md'

# Rotation thresholds
MAX_SIZE_MB = 10
MAX_LINES = 1000


def should_rotate() -> bool:
    """
    Check if log file should be rotated based on size or line count.
    
    Returns:
        bool: True if file exceeds 10 MB or 1000 lines
    """
    if not LOG_FILE.exists():
        return False
    
    # Check file size
    size_mb = LOG_FILE.stat().st_size / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        return True
    
    # Check line count
    try:
        with LOG_FILE.open('r', encoding='utf-8') as f:
            line_count = sum(1 for _ in f)
        if line_count > MAX_LINES:
            return True
    except Exception:
        pass
    
    return False


def compress_log(timestamp: str) -> Path:
    """
    Compress current log file to timestamped gzip archive.
    
    Args:
        timestamp: UTC ISO timestamp for archive filename
    
    Returns:
        Path: Path to compressed archive
    """
    # Create safe filename from timestamp (remove colons and use underscores)
    safe_ts = timestamp.replace(':', '').replace('-', '').replace('+', '_')
    archive_path = ROOT / f'forensics_error_log_{safe_ts}.gz'
    
    try:
        with LOG_FILE.open('rb') as f_in:
            with gzip.open(archive_path, 'wb') as f_out:
                f_out.write(f_in.read())
        return archive_path
    except Exception as e:
        print(f'Error compressing log: {e}')
        raise


def truncate_and_baseline(timestamp: str) -> None:
    """
    Truncate log file and insert baseline entry.
    
    Args:
        timestamp: UTC ISO timestamp for baseline entry
    """
    try:
        baseline = {
            'timestamp': timestamp,
            'message': 'Log rotated',
            'event': 'rotation'
        }
        LOG_FILE.write_text(json.dumps(baseline) + '\n', encoding='utf-8')
    except Exception as e:
        print(f'Error truncating log: {e}')
        raise


def append_audit_marker(timestamp: str) -> None:
    """
    Append audit marker to audit_summary.md.
    
    Args:
        timestamp: UTC ISO timestamp for marker
    """
    try:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_FILE.open('a', encoding='utf-8') as f:
            f.write(f'<!-- FORENSICS_LOG_ROTATED {timestamp} -->\n')
    except Exception as e:
        print(f'Error appending audit marker: {e}')


def main() -> int:
    """
    Main rotation logic.
    
    Returns:
        int: 0 on success, 1 on error
    """
    if not should_rotate():
        print('Log rotation not needed.')
        return 0
    
    try:
        timestamp = utc_now_iso()
        print(f'Rotating forensics log at {timestamp}')
        
        # Compress current log
        archive = compress_log(timestamp)
        print(f'Compressed to: {archive}')
        
        # Truncate and insert baseline
        truncate_and_baseline(timestamp)
        print('Log truncated with baseline entry')
        
        # Append audit marker
        append_audit_marker(timestamp)
        print('Audit marker appended')
        
        return 0
        
    except Exception as e:
        print(f'Error during rotation: {e}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
