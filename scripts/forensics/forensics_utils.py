#!/usr/bin/env python3
"""
Phase XXI - Instruction 111: Shared Forensics Utilities

Centralized forensics helpers for:
- Timezone-aware UTC timestamps
- Atomic JSON writes with backup
- SHA-256 file hashing with fallback
- Error event logging to forensics_error_log.jsonl
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ERROR_LOG = 'forensics_error_log.jsonl'


def utc_now_iso() -> str:
    """Return timezone-aware UTC ISO string."""
    return datetime.now(timezone.utc).isoformat()


def safe_write_json(path: Path, data: Any, indent: int = 2) -> bool:
    """
    Atomic JSON write with backup and error handling.
    
    Returns True on success, False on failure.
    Logs errors to forensics event log.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create backup if file exists
        if path.exists():
            backup = path.with_suffix(path.suffix + '.backup')
            try:
                shutil.copy2(path, backup)
            except Exception:
                pass  # Backup failure shouldn't block write
        
        # Write to temp then atomic rename
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(json.dumps(data, indent=indent), encoding='utf-8')
        temp.replace(path)
        return True
    except Exception as e:
        log_forensics_event({
            'error': 'safe_write_json_failed',
            'file': str(path),
            'exception': str(e)
        })
        return False


def compute_sha256(path: Path, chunk_size: int = 8192) -> str | None:
    """
    Compute SHA-256 file hash with fallback on partial reads.
    
    Returns hex digest string or None on failure.
    """
    try:
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        log_forensics_event({
            'error': 'compute_sha256_failed',
            'file': str(path),
            'exception': str(e)
        })
        return None


def log_forensics_event(event_dict: dict[str, Any]) -> None:
    """
    Append forensics event to forensics_error_log.jsonl under root.
    
    Adds UTC timestamp automatically. Fails silently to avoid breaking workflows.
    """
    try:
        log_path = ROOT / 'forensics' / ERROR_LOG
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ensure timestamp is present
        if 'timestamp' not in event_dict:
            event_dict['timestamp'] = utc_now_iso()
        
        with log_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(event_dict) + '\n')
    except Exception:
        # Fail silently - forensics logging should never break workflows
        pass


def append_audit_marker(marker: str, root_path: Path | None = None) -> None:
    """
    Append audit marker to audit_summary.md.
    
    Used by forensics scripts to maintain audit trail.
    Args:
        marker: The marker string to append
        root_path: Optional root path (defaults to ROOT for normal use, can be overridden for tests)
    """
    try:
        base = root_path if root_path else ROOT
        audit = base / 'audit_summary.md'
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open('a', encoding='utf-8') as f:
            f.write(f'{marker}\n')
    except Exception as e:
        log_forensics_event({
            'error': 'append_audit_marker_failed',
            'marker': marker,
            'exception': str(e)
        })


if __name__ == '__main__':
    # Self-test and marker generation
    ts = utc_now_iso()
    append_audit_marker(f'<!-- FORENSICS_UTILS: CREATED {ts} -->')
    print(f'Forensics utilities module initialized: {ts}')
