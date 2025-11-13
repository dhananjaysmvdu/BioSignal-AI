#!/usr/bin/env python3
"""
Generate an integrity status badge JSON (shields.io endpoint style).
Reads exports/integrity_metrics_registry.csv and computes the mean integrity_score.
Writes badges/integrity_status.json with label/message/color.

Supports optional command-line arguments for custom label and output path.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def mean_integrity(csv_path: Path) -> Optional[float]:
    if not csv_path.exists():
        return None
    try:
        with csv_path.open('r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return None
        header = rows[0]
        try:
            idx = header.index('integrity_score')
        except ValueError:
            return None
        vals = []
        for r in rows[1:]:
            if not r or r[0].startswith('#'):
                continue
            try:
                vals.append(float(r[idx]))
            except Exception:
                continue
        if not vals:
            return None
        return sum(vals) / len(vals)
    except Exception:
        return None


def color_for_score(score: float) -> str:
    if score >= 90:
        return 'green'
    if score >= 70:
        return 'yellow'
    return 'red'


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Generate governance health badge JSON (shields.io endpoint format)'
    )
    parser.add_argument(
        '--input',
        type=Path,
        default=Path('exports/integrity_metrics_registry.csv'),
        help='Path to integrity metrics registry CSV (default: exports/integrity_metrics_registry.csv)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('badges/integrity_status.json'),
        help='Path to output badge JSON (default: badges/integrity_status.json)'
    )
    parser.add_argument(
        '--label',
        type=str,
        default=None,
        help='Badge label (default: derived from output filename)'
    )
    
    args = parser.parse_args()
    
    # Derive label from output filename if not provided
    if args.label is None:
        filename = args.output.stem
        if 'reproducibility' in filename.lower():
            label = 'Reproducibility'
        elif 'integrity' in filename.lower():
            label = 'Integrity'
        else:
            label = 'Health'
    else:
        label = args.label
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mean = mean_integrity(args.input)
    
    if mean is None:
        data = {"label": label, "message": "n/a", "color": "lightgrey"}
    else:
        msg = f"{mean:.0f}%"
        data = {"label": label, "message": msg, "color": color_for_score(mean)}
    
    # Add explicit timestamp for reproducibility validation
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    
    args.output.write_text(json.dumps(data), encoding='utf-8')
    print(f"Badge generated: {args.output}")
    print(f"  Label: {label}, Score: {msg if mean is not None else 'n/a'}, Color: {data['color']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
