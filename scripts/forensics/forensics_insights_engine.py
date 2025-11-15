#!/usr/bin/env python3
"""
Phase XXII - Instruction 116: Forensics Insights Engine

Real-time forensic behavior analysis: pattern detection, anomaly classification,
and metadata dashboards with immutable record preservation.
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Add forensics directory to path for forensics_utils import
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from forensics_utils import utc_now_iso, log_forensics_event, append_audit_marker

FORENSICS_DIR = ROOT / 'forensics'
OUTPUT_FILE = FORENSICS_DIR / 'forensics_insights_report.json'

# Thresholds
FREQUENT_ERROR_THRESHOLD = 3  # errors per day
HIGH_LATENCY_THRESHOLD = 5.0  # seconds


class AnomalyType:
    """Anomaly classification types."""
    IO_LATENCY = 'Type A - IO Latency'
    MISSING_FILE = 'Type B - Missing File'
    SCHEMA_MISMATCH = 'Type C - Schema Mismatch'
    UNKNOWN = 'Type D - Unknown'


def parse_jsonl_file(path: Path) -> list[dict]:
    """Parse JSONL file, return list of parsed records."""
    records = []
    if not path.exists():
        return records
    
    try:
        with path.open('r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    log_forensics_event({
                        'error': 'jsonl_parse_failed',
                        'file': str(path),
                        'line': line_num,
                        'exception': str(e)
                    })
    except Exception as e:
        log_forensics_event({
            'error': 'file_read_failed',
            'file': str(path),
            'exception': str(e)
        })
    
    return records


def parse_gz_archive(path: Path) -> list[dict]:
    """Parse gzipped JSONL archive."""
    records = []
    if not path.exists():
        return records
    
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    log_forensics_event({
                        'error': 'gz_parse_failed',
                        'file': str(path),
                        'line': line_num,
                        'exception': str(e)
                    })
    except Exception as e:
        log_forensics_event({
            'error': 'gz_read_failed',
            'file': str(path),
            'exception': str(e)
        })
    
    return records


def classify_anomaly(record: dict) -> str:
    """Classify anomaly based on error content."""
    error_msg = str(record.get('error', '')).lower()
    exception_msg = str(record.get('exception', '')).lower()
    combined = error_msg + ' ' + exception_msg
    
    # Type A - IO Latency
    if any(keyword in combined for keyword in ['timeout', 'slow', 'latency', 'performance']):
        return AnomalyType.IO_LATENCY
    
    # Type B - Missing File
    if any(keyword in combined for keyword in ['filenotfound', 'missing', 'not found', 'no such file']):
        return AnomalyType.MISSING_FILE
    
    # Type C - Schema Mismatch
    if any(keyword in combined for keyword in ['schema', 'validation', 'type', 'format', 'decode']):
        return AnomalyType.SCHEMA_MISMATCH
    
    return AnomalyType.UNKNOWN


def analyze_patterns(records: list[dict]) -> dict[str, Any]:
    """Analyze patterns in forensic records."""
    error_types = defaultdict(int)
    file_paths = defaultdict(int)
    anomaly_classes = defaultdict(int)
    timestamps = []
    
    for record in records:
        # Extract timestamp
        ts = record.get('timestamp')
        if ts:
            timestamps.append(ts)
        
        # Count error types
        error = record.get('error')
        if error:
            error_types[error] += 1
        
        # Extract file paths
        file_path = record.get('file') or record.get('meta', {}).get('file')
        if file_path:
            file_paths[file_path] += 1
        
        # Classify anomalies
        if error:
            anomaly_class = classify_anomaly(record)
            anomaly_classes[anomaly_class] += 1
    
    # Calculate frequency (errors per day)
    daily_frequency = 0.0
    if timestamps:
        try:
            first_ts = min(timestamps)
            last_ts = max(timestamps)
            first_dt = datetime.fromisoformat(first_ts.replace('Z', '+00:00'))
            last_dt = datetime.fromisoformat(last_ts.replace('Z', '+00:00'))
            duration_days = max((last_dt - first_dt).total_seconds() / 86400, 1.0)
            daily_frequency = len(records) / duration_days
        except Exception as e:
            log_forensics_event({
                'error': 'frequency_calculation_failed',
                'exception': str(e)
            })
    
    return {
        'total_records': len(records),
        'error_types': dict(error_types),
        'top_file_paths': dict(sorted(file_paths.items(), key=lambda x: x[1], reverse=True)[:10]),
        'anomaly_classes': dict(anomaly_classes),
        'daily_frequency': round(daily_frequency, 2),
        'first_timestamp': timestamps[0] if timestamps else None,
        'last_timestamp': timestamps[-1] if timestamps else None,
        'frequent_errors': [error for error, count in error_types.items() 
                           if count / max(duration_days if 'duration_days' in locals() else 1, 1) > FREQUENT_ERROR_THRESHOLD]
    }


def collect_all_records() -> list[dict]:
    """Collect all forensic records from active logs and archives."""
    all_records = []
    
    # Parse active error log
    error_log = FORENSICS_DIR / 'forensics_error_log.jsonl'
    all_records.extend(parse_jsonl_file(error_log))
    
    # Parse verification log
    verification_log = FORENSICS_DIR / 'verification_log.jsonl'
    all_records.extend(parse_jsonl_file(verification_log))
    
    # Parse archived logs
    for archive in sorted(FORENSICS_DIR.glob('forensics_error_log_*.gz')):
        all_records.extend(parse_gz_archive(archive))
    
    return all_records


def generate_insights_report() -> dict[str, Any]:
    """Generate comprehensive forensics insights report."""
    records = collect_all_records()
    
    if not records:
        return {
            'timestamp': utc_now_iso(),
            'total_records': 0,
            'status': 'no_data',
            'message': 'No forensic records found for analysis'
        }
    
    analysis = analyze_patterns(records)
    
    report = {
        'timestamp': utc_now_iso(),
        'status': 'success',
        'summary': {
            'total_records_analyzed': analysis['total_records'],
            'daily_error_frequency': analysis['daily_frequency'],
            'time_range': {
                'first': analysis['first_timestamp'],
                'last': analysis['last_timestamp']
            }
        },
        'error_types': analysis['error_types'],
        'anomaly_classification': analysis['anomaly_classes'],
        'top_affected_files': analysis['top_file_paths'],
        'frequent_errors': analysis['frequent_errors'],
        'alerts': []
    }
    
    # Generate alerts for anomalies
    total_anomalies = sum(analysis['anomaly_classes'].values())
    if total_anomalies > 10:
        report['alerts'].append({
            'severity': 'high',
            'type': 'anomaly_spike',
            'message': f'High anomaly count detected: {total_anomalies} total',
            'timestamp': utc_now_iso()
        })
    
    if analysis['daily_frequency'] > FREQUENT_ERROR_THRESHOLD:
        report['alerts'].append({
            'severity': 'medium',
            'type': 'frequent_errors',
            'message': f'Error frequency ({analysis["daily_frequency"]:.2f}/day) exceeds threshold',
            'timestamp': utc_now_iso()
        })
    
    return report


def main() -> int:
    """Main entry point for forensics insights engine."""
    FORENSICS_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        report = generate_insights_report()
        
        # Write report
        OUTPUT_FILE.write_text(json.dumps(report, indent=2), encoding='utf-8')
        
        # Append audit marker
        ts = utc_now_iso()
        append_audit_marker(f'<!-- FORENSICS_INSIGHTS: UPDATED {ts} -->', ROOT)
        
        # Print summary
        if report['status'] == 'success':
            print(f"FORENSICS_INSIGHTS_GENERATED total={report['summary']['total_records_analyzed']} "
                  f"anomalies={sum(report['anomaly_classification'].values())} "
                  f"alerts={len(report['alerts'])}")
        else:
            print(f"FORENSICS_INSIGHTS_NO_DATA")
        
        return 0
    except Exception as e:
        log_forensics_event({
            'error': 'insights_engine_failed',
            'exception': str(e)
        })
        print(f"FORENSICS_INSIGHTS_FAILED: {e}")
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
