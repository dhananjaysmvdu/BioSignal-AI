from __future__ import annotations

from pathlib import Path
import json

def test_schema_drift_predictor_runs(tmp_path: Path):
    # Execute predictor and verify output file exists and has fields
    import subprocess, sys
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run([sys.executable, str(root/"scripts"/"forecast"/"schema_drift_predictor.py")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = root/"forecast"/"schema_drift_forecast.json"
    assert out.exists(), "Forecast JSON missing"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "drift_prob" in data and "repairs_count" in data
