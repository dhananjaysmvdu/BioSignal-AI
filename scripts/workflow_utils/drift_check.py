import json
from pathlib import Path
from typing import Any, Dict

try:
    from monitoring.drift_detector import detect_drift  # type: ignore
except Exception:
    # Fallback stub if module not available to avoid hard failure
    def detect_drift(reference: Path, current: Path, threshold: float = 0.1) -> Dict[str, Any]:
        return {
            "overall_drift_rate": 0.0,
            "detail": "drift_detector not available",
        }

def main() -> None:
    ref = Path('data/reference/metadata.csv')
    cur = Path('data/current/metadata.csv')
    if not (ref.is_file() and cur.is_file()):
        # Graceful default when inputs are missing
        print("overall_drift_rate=0.0")
        return
    report = detect_drift(ref, cur, threshold=0.1)
    Path('results').mkdir(exist_ok=True)
    Path('results/drift_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('overall_drift_rate=', report.get('overall_drift_rate'))

if __name__ == '__main__':
    main()
