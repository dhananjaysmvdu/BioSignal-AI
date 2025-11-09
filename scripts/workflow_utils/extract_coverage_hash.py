import json
from pathlib import Path

def main():
    p = Path('reports/history/versions.json')
    if not p.exists():
        print('')
        return
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        if isinstance(data, list) and data:
            print(data[-1].get('coverage_badge_hash', ''))
        else:
            print('')
    except Exception:
        print('')

if __name__ == '__main__':
    main()
