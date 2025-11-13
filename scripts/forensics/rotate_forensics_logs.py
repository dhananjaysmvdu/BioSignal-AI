#!/usr/bin/env python3
"""
Phase XXI - Instruction 112: Forensics Log Rotation

Automatically rotates forensics_error_log.jsonl when it exceeds size or line thresholds.
Compresses rotated logs to .gz format and resets the active log.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

# Add forensics directory to path for forensics_utils import
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forensics_utils import utc_now_iso, append_audit_marker
FORENSICS_DIR = ROOT / 'forensics'
ERROR_LOG = FORENSICS_DIR / 'forensics_error_log.jsonl'

# Rotation thresholds
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_LINES = 1000


def count_lines(path: Path) -> int:
    """Count lines in a file efficiently."""
    try:
        with path.open('r', encoding='utf-8') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def needs_rotation() -> bool:
    """Check if log rotation is needed based on size or line count."""
    if not ERROR_LOG.exists():
        return False
    
    try:
        size = ERROR_LOG.stat().st_size
        if size >= MAX_SIZE_BYTES:
            return True
        
        lines = count_lines(ERROR_LOG)
        if lines >= MAX_LINES:
            return True
    except Exception:
        pass
    
    return False


def rotate_log() -> str | None:
    """
    Rotate the forensics error log.
    
    Returns the compressed archive filename on success, None on failure.
    """
    if not ERROR_LOG.exists():
        return None
    
    ts = utc_now_iso().replace(':', '').replace('-', '').replace('+', '').replace('.', '')
    archive_name = f'forensics_error_log_{ts}.gz'
    archive_path = FORENSICS_DIR / archive_name
    
    try:
        # Compress existing log
        with ERROR_LOG.open('rb') as f_in:
            with gzip.open(archive_path, 'wb') as f_out:
                f_out.writelines(f_in)
        
        # Truncate and reset with baseline entry
        baseline = {
            'timestamp': utc_now_iso(),
            'message': 'Log rotated',
            'archive': archive_name
        }
        ERROR_LOG.write_text(json.dumps(baseline) + '\n', encoding='utf-8')
        
        return archive_name
    except Exception as e:
        # Log rotation failure shouldn't break workflows
        # Create minimal error record
        try:
            ERROR_LOG.write_text(
                json.dumps({
                    'timestamp': utc_now_iso(),
                    'error': 'rotation_failed',
                    'exception': str(e)
                }) + '\n',
                encoding='utf-8'
            )
        except Exception:
            pass
        return None


def main() -> int:
    """Main entry point for log rotation."""
    FORENSICS_DIR.mkdir(parents=True, exist_ok=True)
    
    if not needs_rotation():
        print('No rotation needed')
        return 0
    
    archive_name = rotate_log()
    if not archive_name:
        print('Rotation failed')
        return 1
    
    # Add audit marker
    ts = utc_now_iso()
    append_audit_marker(f'<!-- FORENSICS_LOG_ROTATED: {ts} archive={archive_name} -->', ROOT)
    
    print(f'Rotated forensics log to {archive_name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
