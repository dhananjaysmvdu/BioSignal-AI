#!/usr/bin/env python3
"""
Phase XXIII - Instruction 121: Forensic Anomaly Forecaster

Predictive model for anomaly volume forecasting using exponential smoothing.
Outputs 7-day forecast with risk level assessment.
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

from forensics_utils import utc_now_iso, safe_write_json, log_forensics_event, append_audit_marker

FORENSICS_DIR = ROOT / 'forensics'
ERROR_LOG = FORENSICS_DIR / 'forensics_error_log.jsonl'
OUTPUT_FILE = FORENSICS_DIR / 'forensics_anomaly_forecast.json'
AUDIT_FILE = ROOT / 'audit_summary.md'

# Risk thresholds (anomalies per day)
RISK_THRESHOLDS = {
    'low': 10,      # < 10 anomalies/day
    'medium': 25,   # 10-25 anomalies/day
    'high': 25      # > 25 anomalies/day
}

# Exponential smoothing parameter (0-1, higher = more weight on recent data)
ALPHA = 0.3

# Minimum days required for forecasting
MIN_DAYS_REQUIRED = 3


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


def aggregate_daily_anomalies() -> dict[str, int]:
    """
    Aggregate anomaly counts per day from all forensic logs.
    
    Returns:
        Dictionary mapping ISO date strings to anomaly counts.
    """
    daily_counts = defaultdict(int)
    
    # Parse active log
    if ERROR_LOG.exists():
        records = parse_jsonl_file(ERROR_LOG)
        for rec in records:
            if 'timestamp' in rec:
                try:
                    dt = datetime.fromisoformat(rec['timestamp'])
                    date_key = dt.date().isoformat()
                    daily_counts[date_key] += 1
                except (ValueError, TypeError):
                    pass
    
    # Parse rotated archives
    for gz_file in FORENSICS_DIR.glob('forensics_error_log_*.jsonl.gz'):
        records = parse_gz_archive(gz_file)
        for rec in records:
            if 'timestamp' in rec:
                try:
                    dt = datetime.fromisoformat(rec['timestamp'])
                    date_key = dt.date().isoformat()
                    daily_counts[date_key] += 1
                except (ValueError, TypeError):
                    pass
    
    return dict(daily_counts)


def exponential_smoothing_forecast(
    historical_counts: list[int],
    forecast_days: int = 7,
    alpha: float = ALPHA
) -> list[float]:
    """
    Simple exponential smoothing forecast.
    
    Args:
        historical_counts: List of daily anomaly counts (ordered chronologically)
        forecast_days: Number of days to forecast
        alpha: Smoothing parameter (0-1)
    
    Returns:
        List of forecasted counts for next N days.
    """
    if not historical_counts:
        return [0.0] * forecast_days
    
    # Initialize with first value
    smoothed = historical_counts[0]
    
    # Apply exponential smoothing to historical data
    for count in historical_counts[1:]:
        smoothed = alpha * count + (1 - alpha) * smoothed
    
    # Forecast: assume last smoothed value continues (naive approach)
    # More sophisticated: trend detection, seasonal decomposition
    forecast = [smoothed] * forecast_days
    
    return forecast


def calculate_risk_level(forecast: list[float]) -> str:
    """
    Determine risk level based on forecasted anomaly counts.
    
    Args:
        forecast: List of predicted daily anomaly counts
    
    Returns:
        Risk level: 'low', 'medium', or 'high'
    """
    if not forecast:
        return 'low'
    
    avg_forecast = sum(forecast) / len(forecast)
    
    if avg_forecast > RISK_THRESHOLDS['high']:
        return 'high'
    elif avg_forecast > RISK_THRESHOLDS['low']:
        return 'medium'
    else:
        return 'low'


def generate_forecast() -> dict[str, Any]:
    """
    Generate 7-day anomaly forecast with risk assessment.
    
    Returns:
        Forecast report dictionary.
    """
    try:
        # Aggregate historical data
        daily_counts = aggregate_daily_anomalies()
        
        # Insufficient data check
        if len(daily_counts) < MIN_DAYS_REQUIRED:
            log_forensics_event({
                'warning': 'insufficient_data_for_forecast',
                'days_available': len(daily_counts),
                'min_required': MIN_DAYS_REQUIRED
            })
            
            return {
                'status': 'insufficient_data',
                'forecast_generated_at': utc_now_iso(),
                'days_analyzed': len(daily_counts),
                'predicted_anomalies_7d': [0.0] * 7,
                'risk_level': 'low',
                'risk_rationale': f'Insufficient historical data ({len(daily_counts)} days < {MIN_DAYS_REQUIRED} required). Defaulting to low risk.'
            }
        
        # Sort dates and extract counts
        sorted_dates = sorted(daily_counts.keys())
        historical_counts = [daily_counts[date] for date in sorted_dates]
        
        # Generate 7-day forecast
        forecast = exponential_smoothing_forecast(historical_counts, forecast_days=7)
        
        # Assess risk
        risk_level = calculate_risk_level(forecast)
        
        # Build report
        report = {
            'status': 'success',
            'forecast_generated_at': utc_now_iso(),
            'historical_summary': {
                'days_analyzed': len(daily_counts),
                'date_range': {
                    'first': sorted_dates[0],
                    'last': sorted_dates[-1]
                },
                'total_anomalies': sum(historical_counts),
                'avg_daily_anomalies': sum(historical_counts) / len(historical_counts)
            },
            'predicted_anomalies_7d': [round(val, 2) for val in forecast],
            'risk_level': risk_level,
            'risk_rationale': f'Forecasted average: {sum(forecast)/len(forecast):.2f} anomalies/day. Threshold: low<{RISK_THRESHOLDS["low"]}, medium<{RISK_THRESHOLDS["high"]}, high>={RISK_THRESHOLDS["high"]}.',
            'model_parameters': {
                'algorithm': 'exponential_smoothing',
                'alpha': ALPHA,
                'forecast_horizon_days': 7
            }
        }
        
        return report
    
    except Exception as e:
        log_forensics_event({
            'error': 'forecast_generation_failed',
            'exception': str(e),
            'exception_type': type(e).__name__
        })
        
        # Return safe fallback
        return {
            'status': 'error',
            'forecast_generated_at': utc_now_iso(),
            'error': str(e),
            'predicted_anomalies_7d': [0.0] * 7,
            'risk_level': 'low',
            'risk_rationale': 'Forecast generation failed. Defaulting to low risk.'
        }


def main() -> None:
    """Generate forecast and save to file."""
    # Generate forecast
    forecast_report = generate_forecast()
    
    # Write to output file
    success = safe_write_json(OUTPUT_FILE, forecast_report)
    
    if success:
        print(f"Forecast generated: {OUTPUT_FILE}")
        print(f"Risk Level: {forecast_report.get('risk_level', 'unknown')}")
        print(f"Status: {forecast_report.get('status', 'unknown')}")
        
        # Append audit marker
        marker = f"<!-- FORENSICS_FORECAST: UPDATED {utc_now_iso()} -->"
        append_audit_marker(marker, ROOT)
    else:
        print("Failed to write forecast file.", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
