import os
import json
import runpy
from pathlib import Path
import importlib


def test_drift_check_missing_inputs_defaults_zero(tmp_path, capsys):
    # Run in isolated dir without input CSVs
    os.chdir(tmp_path)
    mod = importlib.import_module('scripts.workflow_utils.drift_check')
    importlib.reload(mod)
    mod.main()
    out = capsys.readouterr().out.strip()
    assert 'overall_drift_rate=0.0' in out


def test_parse_drift_valid_and_malformed(tmp_path, capsys):
    os.chdir(tmp_path)
    # Valid JSON case
    results_dir = Path('results')
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / 'drift_report.json').write_text(json.dumps({'overall_drift_rate': 0.23}), encoding='utf-8')
    runpy.run_module('scripts.workflow_utils.parse_drift', run_name='__main__')
    out1 = capsys.readouterr().out.strip()
    assert out1 == '0.23'

    # Malformed JSON -> should print 0
    (results_dir / 'drift_report.json').write_text('{broken json', encoding='utf-8')
    runpy.run_module('scripts.workflow_utils.parse_drift', run_name='__main__')
    out2 = capsys.readouterr().out.strip()
    assert out2 == '0'


def test_junit_summary_wellformed_and_incomplete(tmp_path):
    from scripts.workflow_utils.junit_summary import summarize

    # Missing file
    msg_missing = summarize(tmp_path / 'pytest.xml')
    assert 'No junit report found' in msg_missing

    # Well-formed file
    xml = (
        "<testsuite tests='5' failures='1' errors='0' skipped='2'>"
        "</testsuite>"
    )
    p = tmp_path / 'pytest.xml'
    p.write_text(xml, encoding='utf-8')
    msg_ok = summarize(p)
    assert 'Tests: 5, Failures: 1, Errors: 0, Skipped: 2' in msg_ok

    # Incomplete/invalid XML
    p.write_text('<not-xml', encoding='utf-8')
    msg_bad = summarize(p)
    assert 'Failed to parse junit report' in msg_bad


def test_artifact_integrity_ok_missing_and_mismatch(tmp_path, capsys):
    # Prepare dirs
    os.chdir(tmp_path)
    # Create all expected artifacts for OK case
    files = {
        'reports/BioSignalX_Report.pdf': b'RPT',
        'build/pub/BioSignalX_Manuscript.pdf': b'MS',
        'results/calibration_report.csv': b'a,b\n1,2\n',
        'results/benchmark_metrics.csv': b'a,b\n3,4\n',
        'results/fairness/fairness_summary.json': b'{"ok": true}',
        'docs/manuscript_draft.md': b'# Title',
    }
    for rel, content in files.items():
        p = Path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)

    # OK case (no previous hashes, all present)
    from scripts import artifact_integrity_check as aic
    importlib.reload(aic)
    aic.main()
    status = Path('build/pub/integrity_status.txt').read_text(encoding='utf-8').strip()
    assert status == 'OK'

    # Missing case: remove one artifact
    Path('results/benchmark_metrics.csv').unlink()
    importlib.reload(aic)
    aic.main()
    status2 = Path('build/pub/integrity_status.txt').read_text(encoding='utf-8').strip()
    assert status2 == 'DRIFT'

    # Mismatch case: restore file but set previous hashes to different values
    Path('results/benchmark_metrics.csv').write_text('x,y\n9,9\n', encoding='utf-8')
    # Seed versions.json with different hashes
    hist_dir = Path('reports/history')
    hist_dir.mkdir(parents=True, exist_ok=True)
    versions = [
        {
            "version": "test",
            "integrity_audit": {
                "hashes": {k: 'deadbeef' for k in ['report_pdf','manuscript_pdf','calibration_csv','benchmark_csv','fairness_json','manuscript_md']}
            }
        }
    ]
    (hist_dir / 'versions.json').write_text(json.dumps(versions, indent=2), encoding='utf-8')
    importlib.reload(aic)
    aic.main()
    status3 = Path('build/pub/integrity_status.txt').read_text(encoding='utf-8').strip()
    assert status3 == 'DRIFT'


def test_drift_detector_handles_missing_and_empty(tmp_path):
    from monitoring.drift_detector import detect_drift

    # Missing files
    ref = tmp_path / 'ref.csv'
    cur = tmp_path / 'cur.csv'
    rep = detect_drift(ref, cur, threshold=0.1)
    assert rep['overall_drift_rate'] == 0.0
    assert 'feature_drifts' in rep and isinstance(rep['feature_drifts'], dict)
    assert 'timestamp' in rep

    # Empty files
    ref.write_text('', encoding='utf-8')
    cur.write_text('', encoding='utf-8')
    rep2 = detect_drift(ref, cur, threshold=0.1)
    assert rep2['overall_drift_rate'] == 0.0
    assert 'feature_drifts' in rep2 and isinstance(rep2['feature_drifts'], dict)
    assert 'timestamp' in rep2


def test_drift_detector_output_structure_and_shift(tmp_path):
    from monitoring.drift_detector import detect_drift
    import pandas as pd

    ref = tmp_path / 'ref.csv'
    cur = tmp_path / 'cur.csv'
    # Create synthetic data with a shifted numeric distribution
    pd.DataFrame({'x':[0,0.1,0.2,0.1,0.0, -0.1, 0.05, 0.2, -0.05, 0.1], 'y':['a','a','b','a','b','b','a','b','a','b']}).to_csv(ref, index=False)
    pd.DataFrame({'x':[5,5.2,5.1,4.9,5.3,4.8,5.0,5.4,5.1,5.2], 'y':['a','b','b','b','a','b','b','a','a','b']}).to_csv(cur, index=False)

    rep = detect_drift(ref, cur, threshold=0.1)
    # Required keys present
    for k in ('overall_drift_rate','feature_drifts','timestamp'):
        assert k in rep
    assert isinstance(rep['feature_drifts'], dict)
    # Expect non-zero drift rate due to large shift in 'x'
    assert rep['overall_drift_rate'] > 0.0


def test_forecast_evaluator_correlation_computation(tmp_path):
    """Test Pearson correlation computation in forecast evaluator."""
    from scripts.workflow_utils.governance_reflex_forecast_evaluator import compute_pearson_correlation
    
    # Perfect positive correlation
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    corr = compute_pearson_correlation(x, y)
    assert abs(corr - 1.0) < 0.01
    
    # Perfect negative correlation
    y_neg = [10.0, 8.0, 6.0, 4.0, 2.0]
    corr_neg = compute_pearson_correlation(x, y_neg)
    assert abs(corr_neg + 1.0) < 0.01
    
    # No correlation
    x_rand = [1.0, 2.0, 3.0, 4.0, 5.0]
    y_rand = [3.0, 1.0, 4.0, 2.0, 5.0]
    corr_weak = compute_pearson_correlation(x_rand, y_rand)
    assert abs(corr_weak) < 0.8  # Should be weak
    
    # Edge cases
    assert compute_pearson_correlation([], []) == 0.0
    assert compute_pearson_correlation([1.0], [1.0]) == 0.0  # Need at least 2


def test_forecast_evaluator_classification(tmp_path):
    """Test correlation classification thresholds."""
    from scripts.workflow_utils.governance_reflex_forecast_evaluator import classify_correlation
    
    assert classify_correlation(0.8) == "Aligned improvement"
    assert classify_correlation(0.5) == "Aligned improvement"
    assert classify_correlation(0.49) == "Neutral coupling"
    assert classify_correlation(0.0) == "Neutral coupling"
    assert classify_correlation(-0.49) == "Neutral coupling"
    assert classify_correlation(-0.5) == "Diverging signals"
    assert classify_correlation(-0.8) == "Diverging signals"


def test_forecast_evaluator_end_to_end(tmp_path, capsys):
    """Test forecast evaluator creates alignment report."""
    os.chdir(tmp_path)
    
    # Create minimal input files
    reports = Path('reports')
    reports.mkdir(exist_ok=True)
    
    # Reflex evaluation
    reflex = {
        "rei": 0.15,
        "classification": "Effective",
        "timestamp": "2025-01-15T10:00:00Z"
    }
    (reports / 'reflex_evaluation.json').write_text(json.dumps(reflex), encoding='utf-8')
    
    # Meta-performance
    meta = {
        "mpi": 85.0,
        "classification": "Stable",
        "timestamp": "2025-01-15T10:00:00Z"
    }
    (reports / 'reflex_meta_performance.json').write_text(json.dumps(meta), encoding='utf-8')
    
    # Model history with MPI values showing aligned improvement
    history = [
        {"meta_performance": {"mpi": 75.0}, "timestamp": "2025-01-14T10:00:00Z"},
        {"meta_performance": {"mpi": 78.0}, "timestamp": "2025-01-14T11:00:00Z"},
        {"meta_performance": {"mpi": 80.0}, "timestamp": "2025-01-14T12:00:00Z"},
        {"meta_performance": {"mpi": 82.0}, "timestamp": "2025-01-15T09:00:00Z"},
        {"meta_performance": {"mpi": 85.0}, "timestamp": "2025-01-15T10:00:00Z"}
    ]
    (reports / 'reflex_learning_model.json').write_text(json.dumps(history), encoding='utf-8')
    
    # Run evaluator
    from scripts.workflow_utils.governance_reflex_forecast_evaluator import main
    result = main([
        '--reflex', str(reports / 'reflex_evaluation.json'),
        '--meta-performance', str(reports / 'reflex_meta_performance.json'),
        '--model-history', str(reports / 'reflex_learning_model.json'),
        '--output', str(reports / 'reflex_forecast_alignment.json'),
        '--audit-summary', 'audit_summary.md'
    ])
    
    assert result == 0
    
    # Check output file exists
    alignment_file = reports / 'reflex_forecast_alignment.json'
    assert alignment_file.exists()
    
    # Validate output structure
    alignment = json.loads(alignment_file.read_text(encoding='utf-8'))
    assert 'rei_mpi_correlation' in alignment
    assert 'classification' in alignment
    assert 'n_samples' in alignment
    assert 'timestamp' in alignment
    assert isinstance(alignment['rei_values'], list)
    assert isinstance(alignment['mpi_values'], list)
    
    # Check audit summary updated
    audit = Path('audit_summary.md').read_text(encoding='utf-8')
    assert '<!-- REFLEX_FORECAST:BEGIN -->' in audit
    assert '<!-- REFLEX_FORECAST:END -->' in audit
    assert 'REI-MPI correlation' in audit


def test_consistency_monitor_sign_change(tmp_path):
    """Test consistency monitor detects sign change."""
    from scripts.workflow_utils.governance_forecast_consistency_monitor import detect_inconsistency
    
    # Positive to negative (sign change)
    triggered, status, reasons = detect_inconsistency(0.6, -0.3, "Aligned improvement", "Neutral coupling")
    assert triggered == True
    assert "Sign change detected" in reasons[0]
    assert "⚠️" in status
    
    # Negative to positive (sign change)
    triggered, status, reasons = detect_inconsistency(-0.5, 0.4, "Diverging signals", "Neutral coupling")
    assert triggered == True
    assert "Sign change detected" in reasons[0]


def test_consistency_monitor_divergence_threshold(tmp_path):
    """Test consistency monitor detects divergence threshold."""
    from scripts.workflow_utils.governance_forecast_consistency_monitor import detect_inconsistency
    
    # Below -0.4 threshold
    triggered, status, reasons = detect_inconsistency(-0.2, -0.45, "Neutral coupling", "Diverging signals")
    assert triggered == True
    assert any("divergence threshold" in r for r in reasons)
    
    # Not below threshold
    triggered, status, reasons = detect_inconsistency(-0.2, -0.3, "Neutral coupling", "Neutral coupling")
    assert triggered == False


def test_consistency_monitor_sudden_shift(tmp_path):
    """Test consistency monitor detects sudden correlation shift."""
    from scripts.workflow_utils.governance_forecast_consistency_monitor import detect_inconsistency
    
    # Large shift (> 0.5)
    triggered, status, reasons = detect_inconsistency(0.7, 0.1, "Aligned improvement", "Neutral coupling")
    assert triggered == True
    assert any("Sudden correlation shift" in r for r in reasons)
    
    # Small shift
    triggered, status, reasons = detect_inconsistency(0.5, 0.6, "Aligned improvement", "Aligned improvement")
    assert triggered == False


def test_consistency_monitor_end_to_end(tmp_path, capsys):
    """Test consistency monitor creates full report."""
    os.chdir(tmp_path)
    
    # Create directories
    reports = Path('reports')
    logs = Path('logs')
    reports.mkdir(exist_ok=True)
    logs.mkdir(exist_ok=True)
    
    # Create current alignment
    current_alignment = {
        "timestamp": "2025-01-15T12:00:00Z",
        "rei_mpi_correlation": -0.45,
        "classification": "Diverging signals",
        "n_samples": 5
    }
    (reports / 'reflex_forecast_alignment.json').write_text(json.dumps(current_alignment), encoding='utf-8')
    
    # Create history with previous alignment (sign change scenario)
    history = [
        {
            "timestamp": "2025-01-15T10:00:00Z",
            "rei_mpi_correlation": 0.6,
            "classification": "Aligned improvement",
            "n_samples": 5
        }
    ]
    (logs / 'forecast_alignment_history.json').write_text(json.dumps(history), encoding='utf-8')
    
    # Run monitor
    from scripts.workflow_utils.governance_forecast_consistency_monitor import main
    result = main([
        '--alignment', str(reports / 'reflex_forecast_alignment.json'),
        '--history', str(logs / 'forecast_alignment_history.json'),
        '--output', str(reports / 'forecast_consistency.json'),
        '--audit-summary', 'audit_summary.md'
    ])
    
    assert result == 0
    
    # Check output file
    consistency_file = reports / 'forecast_consistency.json'
    assert consistency_file.exists()
    
    # Validate output structure
    consistency = json.loads(consistency_file.read_text(encoding='utf-8'))
    assert consistency['triggered'] == True
    assert '⚠️' in consistency['status']
    assert consistency['current_correlation'] == -0.45
    assert consistency['previous_correlation'] == 0.6
    assert abs(consistency['delta_correlation'] - (-1.05)) < 0.01
    assert len(consistency['reasons']) > 0
    assert 'Sign change detected' in consistency['reasons'][0]
    
    # Check history updated
    history_file = logs / 'forecast_alignment_history.json'
    assert history_file.exists()
    updated_history = json.loads(history_file.read_text(encoding='utf-8'))
    assert len(updated_history) == 2  # Original + new entry
    
    # Check audit summary
    audit = Path('audit_summary.md').read_text(encoding='utf-8')
    assert '<!-- FORECAST_CONSISTENCY:BEGIN -->' in audit
    assert '<!-- FORECAST_CONSISTENCY:END -->' in audit
    assert 'Forecast Consistency' in audit
