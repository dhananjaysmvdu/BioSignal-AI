import hashlib
from pathlib import Path
import json

def main() -> None:
    badges_sig = Path('badges/coverage.sig')
    hist_dir = Path('reports/history')
    hist_dir.mkdir(parents=True, exist_ok=True)
    versions_path = hist_dir / 'versions.json'

    # Compute SHA256 of the signature file contents (as requested)
    if badges_sig.exists():
        h = hashlib.sha256()
        h.update(badges_sig.read_bytes())
        sig_sha256 = h.hexdigest()
    else:
        sig_sha256 = ''

    data = []
    if versions_path.exists():
        try:
            data = json.loads(versions_path.read_text(encoding='utf-8'))
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []

    if data:
        data[-1]['coverage_badge_hash'] = sig_sha256
    else:
        data.append({'coverage_badge_hash': sig_sha256})

    versions_path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print('coverage_badge_hash:', sig_sha256)

if __name__ == '__main__':
    main()
