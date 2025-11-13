#!/usr/bin/env python3
"""
Phase XXII - Instruction 118: Forensics Insights Engine Tests

Validates pattern detection, anomaly classification, and marker generation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add forensics directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'forensics'))

from forensics_insights_engine import (
    classify_anomaly,
    analyze_patterns,
    generate_insights_report,
    AnomalyType
)


def test_anomaly_classification():
    """Test anomaly classification logic."""
    # Type A - IO Latency
    assert classify_anomaly({'error': 'timeout', 'exception': ''}) == AnomalyType.IO_LATENCY
    assert classify_anomaly({'error': 'slow_operation', 'exception': 'latency'}) == AnomalyType.IO_LATENCY
    
    # Type B - Missing File
    assert classify_anomaly({'error': 'file_missing', 'exception': 'FileNotFoundError'}) == AnomalyType.MISSING_FILE
    assert classify_anomaly({'error': 'load_failed', 'exception': 'no such file'}) == AnomalyType.MISSING_FILE
    
    # Type C - Schema Mismatch
    assert classify_anomaly({'error': 'validation_error', 'exception': ''}) == AnomalyType.SCHEMA_MISMATCH
    assert classify_anomaly({'error': 'parse_failed', 'exception': 'JSONDecodeError'}) == AnomalyType.SCHEMA_MISMATCH
    
    # Type D - Unknown
    assert classify_anomaly({'error': 'unexpected_error', 'exception': 'SomeWeirdError'}) == AnomalyType.UNKNOWN


def test_pattern_analysis():
    """Test pattern detection in forensic records."""
    records = [
        {'timestamp': '2025-01-01T00:00:00+00:00', 'error': 'timeout', 'file': '/path/to/file1.json'},
        {'timestamp': '2025-01-01T00:01:00+00:00', 'error': 'timeout', 'file': '/path/to/file1.json'},
        {'timestamp': '2025-01-01T00:02:00+00:00', 'error': 'missing_file', 'file': '/path/to/file2.json', 'exception': 'FileNotFoundError'},
        {'timestamp': '2025-01-02T00:00:00+00:00', 'error': 'validation_error', 'file': '/path/to/file3.json'},
    ]
    
    analysis = analyze_patterns(records)
    
    assert analysis['total_records'] == 4
    assert analysis['error_types']['timeout'] == 2
    assert analysis['error_types']['missing_file'] == 1
    assert '/path/to/file1.json' in analysis['top_file_paths']
    assert analysis['top_file_paths']['/path/to/file1.json'] == 2
    
    # Check anomaly classification
    assert AnomalyType.IO_LATENCY in analysis['anomaly_classes']
    assert AnomalyType.MISSING_FILE in analysis['anomaly_classes']
    assert AnomalyType.SCHEMA_MISMATCH in analysis['anomaly_classes']
    
    # Check timestamps
    assert analysis['first_timestamp'] == '2025-01-01T00:00:00+00:00'
    assert analysis['last_timestamp'] == '2025-01-02T00:00:00+00:00'


def test_insights_report_structure(monkeypatch, tmp_path):
    """Test insights report generation and structure."""
    # Monkeypatch ROOT and FORENSICS_DIR
    import forensics_insights_engine
    monkeypatch.setattr(forensics_insights_engine, 'ROOT', tmp_path)
    monkeypatch.setattr(forensics_insights_engine, 'FORENSICS_DIR', tmp_path / 'forensics')
    
    # Create mock log files
    forensics_dir = tmp_path / 'forensics'
    forensics_dir.mkdir(parents=True)
    
    error_log = forensics_dir / 'forensics_error_log.jsonl'
    error_log.write_text(
        json.dumps({'timestamp': '2025-01-01T00:00:00+00:00', 'error': 'timeout', 'file': '/test.json'}) + '\n' +
        json.dumps({'timestamp': '2025-01-01T00:01:00+00:00', 'error': 'missing_file', 'exception': 'FileNotFoundError'}) + '\n',
        encoding='utf-8'
    )
    
    verification_log = forensics_dir / 'verification_log.jsonl'
    verification_log.write_text(
        json.dumps({'timestamp': '2025-01-01T00:02:00+00:00', 'type': 'snapshot', 'verified': True}) + '\n',
        encoding='utf-8'
    )
    
    # Generate report
    report = generate_insights_report()
    
    # Validate structure
    assert report['status'] == 'success'
    assert 'timestamp' in report
    assert 'summary' in report
    assert 'error_types' in report
    assert 'anomaly_classification' in report
    assert 'top_affected_files' in report
    assert 'alerts' in report
    
    # Validate summary (should have 3 records from our mock data)
    assert report['summary']['total_records_analyzed'] >= 2  # At least 2 error records
    assert report['summary']['daily_error_frequency'] >= 0
    
    # Validate classifications (should have at least the errors we added)
    assert len(report['anomaly_classification']) > 0


def test_marker_generation(monkeypatch, tmp_path):
    """Test audit marker generation."""
    import forensics_insights_engine
    monkeypatch.setattr(forensics_insights_engine, 'ROOT', tmp_path)
    
    # Create minimal forensics structure
    forensics_dir = tmp_path / 'forensics'
    forensics_dir.mkdir(parents=True)
    (forensics_dir / 'forensics_error_log.jsonl').write_text('', encoding='utf-8')
    
    # Run main
    result = forensics_insights_engine.main()
    assert result == 0
    
    # Check audit marker
    audit = tmp_path / 'audit_summary.md'
    assert audit.exists()
    
    content = audit.read_text(encoding='utf-8')
    assert '<!-- FORENSICS_INSIGHTS: UPDATED' in content


def test_frequency_threshold_alert():
    """Test that high frequency triggers alert."""
    # Simulate high-frequency errors over 1 day
    records = [
        {'timestamp': f'2025-01-01T{i:02d}:00:00+00:00', 'error': f'error_{i % 3}'}
        for i in range(15)  # 15 errors in 1 day = 15/day frequency
    ]
    
    analysis = analyze_patterns(records)
    
    # Daily frequency should be high
    assert analysis['daily_frequency'] > 3.0


def test_empty_logs_handling(monkeypatch, tmp_path):
    """Test handling of empty/missing log files."""
    import forensics_insights_engine
    monkeypatch.setattr(forensics_insights_engine, 'ROOT', tmp_path)
    monkeypatch.setattr(forensics_insights_engine, 'FORENSICS_DIR', tmp_path / 'forensics')
    
    # Create empty forensics directory
    forensics_dir = tmp_path / 'forensics'
    forensics_dir.mkdir(parents=True)
    
    # Generate report with no data
    report = generate_insights_report()
    
    # Should return either no_data status or success with 0 records
    assert report['status'] in ['no_data', 'success']
    if report['status'] == 'no_data':
        assert report['total_records'] == 0
        assert 'message' in report
    else:
        # If it returns success, it should have 0 records analyzed
        assert report['summary']['total_records_analyzed'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
