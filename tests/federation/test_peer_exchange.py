from __future__ import annotations

from pathlib import Path
import json

def test_peer_exchange_runs():
    import subprocess, sys
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run([sys.executable, str(root/"scripts"/"federation"/"federation_peer_exchange.py")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = root/"results"/"federation_peer_exchange_report.json"
    assert out.exists(), "Peer exchange report missing"
    data = json.loads(out.read_text(encoding='utf-8'))
    assert 'peers_compared' in data
