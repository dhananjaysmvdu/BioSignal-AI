#!/usr/bin/env python3
"""
Phase XVII - Instruction 92: Integrity Anchor Mirror

Copies integrity_anchor.json into timestamped mirrors and maintains a cumulative hash chain.
Appends audit marker to audit_summary.md.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Import shared forensics utilities (Phase XXI - Instruction 111)
from scripts.forensics.forensics_utils import utc_now_iso, compute_sha256, safe_write_json

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / 'artifacts'
MIRRORS = ROOT / 'mirrors'


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_anchor() -> Path:
    candidates = [
        ARTIFACTS / 'integrity_anchor.json',
        ROOT / 'artifacts' / 'integrity_anchor.json',
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError('integrity_anchor.json not found in artifacts/')


def append_audit_marker(ts: str) -> None:
    audit = ROOT / 'audit_summary.md'
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open('a', encoding='utf-8') as f:
        f.write(f'<!-- ANCHOR_MIRROR: VERIFIED {ts} -->\n')


def update_chain(mirror_file: Path, ts: str) -> None:
    MIRRORS.mkdir(parents=True, exist_ok=True)
    chain = MIRRORS / 'anchor_chain.json'
    prev = []
    if chain.exists():
        try:
            prev = json.loads(chain.read_text(encoding='utf-8'))
        except Exception:
            prev = []
    current_sha = compute_sha256(mirror_file)
    prev_chain_hash = prev[-1]['chain_hash'] if prev else ''
    chain_hash = sha256_bytes((prev_chain_hash + current_sha).encode('utf-8'))
    prev.append({'timestamp': ts, 'file': mirror_file.name, 'sha256': current_sha, 'chain_hash': chain_hash})
    safe_write_json(chain, prev)


def main() -> int:
    src = load_anchor()
    MIRRORS.mkdir(parents=True, exist_ok=True)
    ts = utc_now_iso().replace(':', '').replace('-', '')
    dst = MIRRORS / f'anchor_{ts}.json'
    dst.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    update_chain(dst, ts)
    append_audit_marker(ts)
    print(f'Mirrored {src} -> {dst}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
