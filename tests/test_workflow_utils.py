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
