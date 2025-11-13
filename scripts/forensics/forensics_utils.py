#!/usr/bin/env python3
"""
Phase XXI - Instruction 111: Shared Forensics Utilities

Centralized utilities for forensics layer operations:
- utc_now_iso(): Returns timezone-aware UTC ISO string
- safe_write_json(path, data): Atomic JSON write with backup and error handling
- compute_sha256(path): SHA-256 file hash with fallback on partial reads
- log_forensics_event(event_dict): Appends to forensics_error_log.jsonl with UTC timestamp

<!-- FORENSICS_UTILS: CREATED 2025-11-13T22:55:19+00:00 -->
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def utc_now_iso() -> str:
    """
    Return timezone-aware UTC ISO timestamp.
    
    Returns:
        str: ISO 8601 formatted UTC timestamp with timezone info (e.g., "2025-01-01T00:00:00+00:00")
    """
    try:
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        # Fallback to basic format if something goes wrong
        return datetime.utcnow().isoformat() + '+00:00'


def safe_write_json(path: Path | str, data: Any) -> bool:
    """
    Atomically write JSON data to a file with backup and error handling.
    
    Creates a backup of existing file before writing, uses temporary file
    for atomic write, and logs errors to forensics_error_log.jsonl on failure.
    
    Args:
        path: Target file path (Path object or string)
        data: Data to serialize as JSON
    
    Returns:
        bool: True if write succeeded, False otherwise
    """
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Create backup if file exists
        if target.exists():
            try:
                backup = target.with_suffix(target.suffix + '.backup')
                shutil.copy2(target, backup)
            except Exception:
                # Continue even if backup fails
                pass
        
        # Write to temporary file first
        tmp = target.with_suffix(target.suffix + '.tmp')
        tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        
        # Atomic rename
        tmp.replace(target)
        return True
        
    except Exception as e:
        # Log the error
        log_forensics_event({
            'operation': 'safe_write_json',
            'path': str(path),
            'error': str(e),
            'error_type': type(e).__name__
        })
        return False


def compute_sha256(path: Path | str) -> str:
    """
    Compute SHA-256 hash of a file with fallback on partial reads.
    
    Reads file in chunks to handle large files efficiently. Returns
    empty string on error (logged to forensics_error_log.jsonl).
    
    Args:
        path: File path to hash (Path object or string)
    
    Returns:
        str: Hex-encoded SHA-256 hash, or empty string on error
    """
    try:
        filepath = Path(path)
        if not filepath.exists():
            log_forensics_event({
                'operation': 'compute_sha256',
                'path': str(path),
                'error': 'File not found',
                'error_type': 'FileNotFoundError'
            })
            return ''
        
        h = hashlib.sha256()
        with filepath.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
        
    except Exception as e:
        log_forensics_event({
            'operation': 'compute_sha256',
            'path': str(path),
            'error': str(e),
            'error_type': type(e).__name__
        })
        return ''


def log_forensics_event(event_dict: dict[str, Any]) -> None:
    """
    Append forensics event to forensics_error_log.jsonl at repository root.
    
    Automatically adds UTC timestamp to event. Creates log file and parent
    directories if they don't exist. Silently fails to avoid breaking workflows.
    
    Args:
        event_dict: Event data to log (timestamp added automatically)
    """
    try:
        log_file = ROOT / 'forensics_error_log.jsonl'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Add timestamp if not present
        if 'timestamp' not in event_dict:
            event_dict['timestamp'] = utc_now_iso()
        
        # Append to log file
        with log_file.open('a', encoding='utf-8') as f:
            f.write(json.dumps(event_dict) + '\n')
            
    except Exception:
        # Silently fail to avoid breaking workflows
        pass
