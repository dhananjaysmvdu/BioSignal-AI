from __future__ import annotations

from pathlib import Path
import json

def test_meta_governance_learning_runs():
    import subprocess, sys
    root = Path(__file__).resolve().parents[2]
    # Ensure a minimal peer exchange exists
    (root/"results").mkdir(parents=True, exist_ok=True)
    (root/"results"/"federation_peer_exchange_report.json").write_text(json.dumps({"peers": []}), encoding='utf-8')
    proc = subprocess.run([sys.executable, str(root/"scripts"/"ai"/"meta_governance_learning.py")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = root/"governance"/"meta_policy_recommendations.json"
    assert out.exists(), "Meta policy recommendations missing"
