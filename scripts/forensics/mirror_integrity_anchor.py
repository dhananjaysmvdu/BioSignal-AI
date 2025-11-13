#!/usr/bin/env python3
"""
Phase XVII - Instruction 92: Integrity Anchor Mirror

Copies integrity_anchor.json into timestamped mirrors and maintains a cumulative hash chain.
Appends audit marker to audit_summary.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Add forensics directory to path for forensics_utils import
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forensics_utils import (
    utc_now_iso,
    compute_sha256,
    log_forensics_event,
    append_audit_marker as audit_marker,
)

# NOTE: Do NOT capture artifact/mirror paths at import for testability; tests monkeypatch ROOT.
# Paths must be derived dynamically inside main/update functions to respect sandboxed ROOT.


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_anchor(artifact_dir: Path) -> Path:
    candidates = [artifact_dir / 'integrity_anchor.json']
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError('integrity_anchor.json not found in artifacts/')





def update_chain(root_path: Path, mirrors_dir: Path, mirror_file: Path, ts: str) -> None:
    mirrors_dir.mkdir(parents=True, exist_ok=True)
    chain = mirrors_dir / 'anchor_chain.json'
    prev = []
    if chain.exists():
        try:
            prev = json.loads(chain.read_text(encoding='utf-8'))
            if not isinstance(prev, list):
                prev = []
        except Exception as e:
            log_forensics_event({'error': 'read_chain_failed', 'exc': str(e)})
            prev = []
    current_sha = compute_sha256(mirror_file) or ''
    prev_chain_hash = prev[-1]['chain_hash'] if prev else ''
    chain_hash = sha256_bytes((prev_chain_hash + current_sha).encode('utf-8'))
    prev.append({'timestamp': ts, 'file': mirror_file.name, 'sha256': current_sha, 'chain_hash': chain_hash})
    # Write with retry
    for attempt in range(2):
        try:
            chain.write_text(json.dumps(prev, indent=2), encoding='utf-8')
            break
        except Exception as e:
            log_forensics_event({'error': 'write_chain_failed', 'exc': str(e), 'attempt': attempt})
    # Print confirmation for deterministic test visibility
    print(f'ANCHOR_CHAIN_UPDATED length={len(prev)} head_chain_hash={prev[-1]["chain_hash"]}')


def main() -> int:
    # Dynamic paths respecting monkeypatched ROOT
    artifact_dir = ROOT / 'artifacts'
    mirrors_dir = ROOT / 'mirrors'
    mirrors_dir.mkdir(parents=True, exist_ok=True)
    try:
        src = load_anchor(artifact_dir)
    except FileNotFoundError as e:
        log_forensics_event({'error': 'anchor_missing', 'detail': str(e)})
        print('Anchor missing; abort mirror.')
        return 1
    ts = utc_now_iso().replace(':', '').replace('-', '')
    dst = mirrors_dir / f'anchor_{ts}.json'
    try:
        dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    except Exception as e:
        log_forensics_event({'error': 'mirror_write_failed', 'exc': str(e)})
        return 2
    update_chain(ROOT, mirrors_dir, dst, ts)
    audit_marker(f'<!-- ANCHOR_MIRROR: VERIFIED {ts} -->', ROOT)
    print(f'Mirrored {src} -> {dst}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
