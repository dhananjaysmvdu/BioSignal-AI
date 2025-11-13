from __future__ import annotations

from pathlib import Path
import json

def test_ethics_sync_runs():
    import subprocess, sys
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run([sys.executable, str(root/"scripts"/"ethics"/"sync_ethics_across_peers.py")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    log = root/"ethics"/"ethics_sync_log.jsonl"
    assert log.exists(), "Ethics sync log missing"
    lines = log.read_text(encoding='utf-8').splitlines()
    assert len(lines) >= 1
