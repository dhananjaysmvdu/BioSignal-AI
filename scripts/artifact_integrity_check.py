import hashlib
import json
from pathlib import Path
from datetime import datetime

ARTIFACTS = {
    'report_pdf': 'reports/BioSignalX_Report.pdf',
    'manuscript_pdf': 'build/pub/BioSignalX_Manuscript.pdf',
    'calibration_csv': 'results/calibration_report.csv',
    'benchmark_csv': 'results/benchmark_metrics.csv',
    'fairness_json': 'results/fairness/fairness_summary.json',
    'manuscript_md': 'docs/manuscript_draft.md',
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    hashes = {}
    missing = []
    for key, rel in ARTIFACTS.items():
        p = Path(rel)
        if p.exists() and p.is_file():
            try:
                hashes[key] = sha256(p)
            except Exception:
                hashes[key] = None
        else:
            hashes[key] = None
            missing.append(key)

    versions_path = Path('reports/history/versions.json')
    prev_hashes = {}
    if versions_path.exists():
        try:
            data = json.loads(versions_path.read_text(encoding='utf-8'))
            if data:
                last = data[-1]
                ia = last.get('integrity_audit', {})
                prev_hashes = ia.get('hashes', {}) if isinstance(ia, dict) else {}
        except Exception:
            pass

    mismatches = []
    for k, current in hashes.items():
        prev = prev_hashes.get(k)
        if prev and current and prev != current:
            mismatches.append(k)

    integrity_ok = (not mismatches) and (len(missing) == 0)

    # Append/augment versions.json (update last entry integrity_audit)
    if versions_path.exists():
        try:
            data = json.loads(versions_path.read_text(encoding='utf-8'))
        except Exception:
            data = []
    else:
        data = []
    if data:
        data[-1]['integrity_audit'] = {
            'timestamp_utc': datetime.utcnow().isoformat() + 'Z',
            'integrity_ok': integrity_ok,
            'mismatches': mismatches,
            'missing': missing,
            'hashes': hashes,
        }
        versions_path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    status_file = Path('build/pub/integrity_status.txt')
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text('OK' if integrity_ok else 'DRIFT', encoding='utf-8')

    print('Integrity OK:', integrity_ok)
    if mismatches:
        print('Mismatches:', mismatches)
    if missing:
        print('Missing:', missing)


if __name__ == '__main__':
    main()
