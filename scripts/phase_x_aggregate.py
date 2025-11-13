"""Aggregate Phase X validation status (used by integration_validation workflow)."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent

def main():
    report = {
        'timestamp_utc': datetime.utcnow().isoformat()+"Z",
        'integration_harness_ok': not (ROOT/'integration_failure.flag').exists(),
        'self_healing_regression_ok': not (ROOT/'self_healing_failure.flag').exists(),
        'guardrail_ok': not (ROOT/'guardrail_failure.flag').exists(),
    }
    out = ROOT/'results'/'phase_x_validation_snapshot.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    if not all(report.values()):
        raise SystemExit(1)

if __name__ == '__main__':
    main()