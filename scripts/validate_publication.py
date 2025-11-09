#!/usr/bin/env python3
"""Validate publication artifacts for completeness before commit.

Normal mode:
    Writes OK or FAIL to build/pub/validation_status.txt and exits 0.
Dry-run mode (--dry-run):
    Prints status and exits with code 0 if OK, 1 if FAIL (used by self-test job).
"""
from __future__ import annotations
import os, json
from pathlib import Path

OUT = Path('build/pub')
OUT.mkdir(parents=True, exist_ok=True)
status_file = OUT / 'validation_status.txt'

required_files = [
    'reports/BioSignalX_Report.pdf',
    'results/calibration_report.csv',
    'results/benchmark_metrics.csv',
    'results/fairness/fairness_summary.json',
    'docs/manuscript_draft.md',
]

missing: list[str] = []

def exists_nonempty(p: str) -> bool:
    path = Path(p)
    return path.exists() and (path.is_dir() or path.stat().st_size > 0)

for rf in required_files:
    if not exists_nonempty(rf):
        missing.append(rf)

ok = True
reasons: list[str] = []
versions_path = Path('reports/history/versions.json')
if not exists_nonempty(str(versions_path)):
    ok = False
    reasons.append('versions.json missing or empty')
else:
    try:
        data = json.loads(versions_path.read_text(encoding='utf-8'))
        if not data:
            ok = False
            reasons.append('versions.json has no entries')
    except Exception as e:  # pragma: no cover
        ok = False
        reasons.append(f'versions.json unreadable: {e}')

if missing:
    ok = False
    reasons.append('missing: ' + ', '.join(missing))

import sys
dry_run = '--dry-run' in sys.argv

if ok:
    print('Report validation passed. All required artifacts present.')
    status_file.write_text('OK', encoding='utf-8')
    if dry_run:
        sys.exit(0)
else:
    print('Report validation failed — skipping commit (missing or incomplete artifacts).')
    for r in reasons:
        print('-', r)
    status_file.write_text('FAIL', encoding='utf-8')
    if dry_run:
        sys.exit(1)
