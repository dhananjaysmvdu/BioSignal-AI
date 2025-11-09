import json
from pathlib import Path

path = Path('results/drift_report.json')
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        rate = data.get('overall_drift_rate', 0)
        # Print number only, for easy shell capture
        print(rate)
    except Exception:
        print(0)
else:
    print(0)
