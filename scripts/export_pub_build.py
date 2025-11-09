"""Build combined publication HTML and version metadata.

Outputs:
    build/pub/combined.html
    reports/history/versions.json (appended)
    build/pub/versioned_name.txt

Adds Performance Change Log section based on previous version.
"""
from __future__ import annotations
import os
import json
from pathlib import Path
from datetime import datetime
import sqlite3
import base64
import subprocess

def main():
    ROOT = Path('.')
    DOCS = ROOT / 'docs'
    RESULTS = ROOT / 'results'
    LOGS = ROOT / 'logs'
    BUILD = ROOT / 'build' / 'pub'
    BUILD.mkdir(parents=True, exist_ok=True)

    def read_p(p):
        p = Path(p)
        return p.read_text(encoding='utf-8') if p.exists() else ''

    readme = read_p('README.md')
    comp = read_p(DOCS / 'compliance_guidelines.md')
    lit = read_p(DOCS / 'literature_summary.md')
    calib = read_p(RESULTS / 'calibration_report.csv')
    bench = read_p(RESULTS / 'benchmark_metrics.csv')
    audit = read_p(LOGS / 'audit_trail.csv')

    # Collect figure artifacts
    FIG_DIR = RESULTS / 'plots'
    figs = {
        'roc': FIG_DIR / 'roc.png',
        'pr': FIG_DIR / 'pr.png',
        'calibration': FIG_DIR / 'calibration.png',
        'uncertainty': FIG_DIR / 'uncertainty.png',
    }
    embedded_imgs = []
    for label, path in figs.items():
        if path.exists():
            b64 = base64.b64encode(path.read_bytes()).decode('utf-8')
            embedded_imgs.append(
                f"<h3>{label.title()} Curve</h3><img src='data:image/png;base64,{b64}' alt='{label} plot' style='width:80%;border:1px solid #ddd;padding:4px;margin-bottom:12px;' />"
            )
        else:
            embedded_imgs.append(
                f"<h3>{label.title()} Curve</h3><p style='color:#999;'>Not available</p>"
            )

    # MLflow summary (SQLite or directory)
    mlflow_summary = "<p style='color:#999;'>No MLflow tracking data found.</p>"
    mlflow_db = ROOT / 'mlflow.db'
    mlruns_dir = ROOT / 'mlruns'
    if mlflow_db.exists():
        try:
            conn = sqlite3.connect(str(mlflow_db))
            cur = conn.cursor()
            cur.execute("SELECT run_uuid, start_time FROM runs ORDER BY start_time DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                run_id, start_time = row
                def get_metric(key):
                    cur.execute("SELECT value FROM metrics WHERE run_uuid=? AND key=? ORDER BY step DESC LIMIT 1", (run_id, key))
                    m = cur.fetchone()
                    return m[0] if m else None
                auc_m = get_metric('AUC') or get_metric('auc') or get_metric('roc_auc')
                ece_m = get_metric('ECE') or get_metric('ece')
                loss_m = get_metric('loss') or get_metric('val_loss')
                acc_m = get_metric('accuracy') or get_metric('acc')
                def get_tag(key):
                    cur.execute("SELECT value FROM tags WHERE run_uuid=? AND key=? LIMIT 1", (run_id, key))
                    t = cur.fetchone()
                    return t[0] if t else None
                phase = get_tag('phase')
                reg = get_tag('regulatory_ready')
                mlflow_summary = f"""
                <table style='border-collapse:collapse;'>
                <tr><th colspan='2' style='text-align:left;padding:4px;border-bottom:1px solid #ccc;'>Latest MLflow Run</th></tr>
                <tr><td style='padding:4px;'>Run ID</td><td style='padding:4px;'>{run_id}</td></tr>
                <tr><td style='padding:4px;'>Start Time</td><td style='padding:4px;'>{start_time}</td></tr>
                <tr><td style='padding:4px;'>Phase</td><td style='padding:4px;'>{phase or 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>Regulatory Ready</td><td style='padding:4px;'>{reg or 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>AUC</td><td style='padding:4px;'>{auc_m if auc_m is not None else 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>ECE</td><td style='padding:4px;'>{ece_m if ece_m is not None else 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>Loss</td><td style='padding:4px;'>{loss_m if loss_m is not None else 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>Accuracy</td><td style='padding:4px;'>{acc_m if acc_m is not None else 'N/A'}</td></tr>
                </table>
                """
            conn.close()
        except Exception as e:
            mlflow_summary = f"<p style='color:#c00;'>Failed to read MLflow DB: {e}</p>"
    elif mlruns_dir.exists():
        try:
            import yaml
            latest_meta = None
            latest_time = -1
            for meta in mlruns_dir.rglob('meta.yaml'):
                try:
                    data = yaml.safe_load(meta.read_text(encoding='utf-8'))
                    st = data.get('start_time', -1)
                    if st and st > latest_time:
                        latest_time = st
                        latest_meta = data
                except Exception:
                    continue
            if latest_meta:
                run_id = latest_meta.get('run_id') or latest_meta.get('run_uuid')
                start_time = latest_meta.get('start_time')
                auc_m = ece_m = loss_m = acc_m = None
                run_dir = mlruns_dir / str(latest_meta.get('experiment_id', '0')) / str(run_id)
                for mfile in run_dir.glob('metrics/*'):
                    try:
                        key = mfile.name
                        val_lines = mfile.read_text(encoding='utf-8').strip().splitlines()
                        if val_lines:
                            last_line = val_lines[-1].split()
                            val = float(last_line[0])
                            if key.lower() in ['auc','roc_auc','auroc','rocauc']:
                                auc_m = val
                            elif key.lower() == 'ece':
                                ece_m = val
                            elif key.lower() in ['loss','val_loss']:
                                loss_m = val
                            elif key.lower() in ['accuracy','acc']:
                                acc_m = val
                    except Exception:
                        continue
                tags_file = run_dir / 'tags' / 'tags.yaml'
                phase = reg = None
                if tags_file.exists():
                    try:
                        tag_data = yaml.safe_load(tags_file.read_text(encoding='utf-8'))
                        phase = tag_data.get('phase')
                        reg = tag_data.get('regulatory_ready')
                    except Exception:
                        pass
                mlflow_summary = f"""
                <table style='border-collapse:collapse;'>
                <tr><th colspan='2' style='text-align:left;padding:4px;border-bottom:1px solid #ccc;'>Latest MLflow Run</th></tr>
                <tr><td style='padding:4px;'>Run ID</td><td style='padding:4px;'>{run_id or 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>Start Time</td><td style='padding:4px;'>{start_time or 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>Phase</td><td style='padding:4px;'>{phase or 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>Regulatory Ready</td><td style='padding:4px;'>{reg or 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>AUC</td><td style='padding:4px;'>{auc_m if auc_m is not None else 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>ECE</td><td style='padding:4px;'>{ece_m if ece_m is not None else 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>Loss</td><td style='padding:4px;'>{loss_m if loss_m is not None else 'N/A'}</td></tr>
                <tr><td style='padding:4px;'>Accuracy</td><td style='padding:4px;'>{acc_m if acc_m is not None else 'N/A'}</td></tr>
                </table>
                """
        except Exception as e:
            mlflow_summary = f"<p style='color:#c00;'>Failed to parse mlruns: {e}</p>"

    title = 'BioSignal-X: Autonomous Clinical AI Governance Report'
    author = 'Auto-Export'
    ts = datetime.utcnow().isoformat() + 'Z'

    html = f"""
    <!doctype html>
    <html lang='en'>
    <head>
      <meta charset='utf-8'/>
      <meta name='viewport' content='width=device-width, initial-scale=1'/>
      <title>{title}</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; }}
        h1,h2,h3 {{ color: #111; }}
        pre, code {{ font-family: Consolas, monospace; font-size: 12px; }}
        .cover {{ border-bottom: 1px solid #ddd; margin-bottom: 24px; padding-bottom: 12px; }}
        .section {{ margin: 18px 0; }}
        .mono {{ white-space: pre-wrap; background: #fafafa; border: 1px solid #eee; padding: 10px; }}
      </style>
    </head>
    <body>
      <div class='cover'>
        <h1>{title}</h1>
        <p>Author: {author}</p>
        <p>Generated: {ts}</p>
      </div>

      <div class='section'>
        <h2>Model Performance Visualization</h2>
        {''.join(embedded_imgs)}
      </div>

      <div class='section'>
        <h2>Latest MLflow Summary</h2>
        {mlflow_summary}
      </div>

      <div class='section'>
        <h2>README</h2>
        <div class='mono'>{readme.replace('<','&lt;').replace('>','&gt;')}</div>
      </div>

      <div class='section'>
        <h2>Compliance Guidelines</h2>
        <div class='mono'>{comp.replace('<','&lt;').replace('>','&gt;')}</div>
      </div>

      <div class='section'>
        <h2>Literature Summary</h2>
        <div class='mono'>{lit.replace('<','&lt;').replace('>','&gt;')}</div>
      </div>

      <div class='section'>
        <h2>Evaluation Artifacts</h2>
        <h3>Calibration Report (CSV)</h3>
        <pre class='mono'>{calib}</pre>
        <h3>Benchmark Metrics (CSV)</h3>
        <pre class='mono'>{bench}</pre>
        <h3>Audit Trail (CSV)</h3>
        <pre class='mono'>{audit}</pre>
      </div>
    </body>
    </html>
    """

    (BUILD / 'combined.html').write_text(html, encoding='utf-8')
    print('Built combined HTML')

    # --- Versioning & performance delta tracking ---
    # Attempt to extract key metrics (AUC/ECE/Drift + incident counts) from existing artifacts.
    auc_val = None
    ece_val = None
    drift_val = None
    try:
        if bench:
            for line in bench.splitlines():
                low = line.lower()
                if 'auc' in low and ',' in line:
                    parts = [p for p in line.replace(';',',').split(',') if p.strip()]
                    for p in parts:
                        try:
                            v = float(p)
                            if 0 <= v <= 1.5:
                                auc_val = v
                                raise StopIteration
                        except Exception:
                            continue
        if calib:
            for line in calib.splitlines():
                low = line.lower()
                if 'ece' in low and ',' in line:
                    parts = [p for p in line.replace(';',',').split(',') if p.strip()]
                    for p in parts:
                        try:
                            v = float(p)
                            if 0 <= v <= 1:
                                ece_val = v
                                raise StopIteration
                        except Exception:
                            continue
    except StopIteration:
        pass

    fairness_summary_path = RESULTS / 'fairness_summary.json'
    drift_report_path = RESULTS / 'drift_report.json'
    try:
        if drift_report_path.exists():
            d = json.loads(drift_report_path.read_text(encoding='utf-8'))
            def deep_find(o):
                if isinstance(o, dict):
                    for k,v in o.items():
                        if 'drift' in k.lower() and isinstance(v,(int,float)):
                            return float(v)
                    for v in o.values():
                        r = deep_find(v)
                        if r is not None:
                            return r
                if isinstance(o, list):
                    for it in o:
                        r = deep_find(it)
                        if r is not None:
                            return r
                return None
            drift_val = deep_find(d)
    except Exception:
        pass

    high = med = lowc = 0
    if audit:
        lines = audit.splitlines()
        if len(lines) > 1:
            for line in lines[1:]:
                parts = line.split(',')
                if len(parts) >= 6:
                    sev = parts[5].strip()
                    if sev == 'High':
                        high += 1
                    elif sev == 'Medium':
                        med += 1
                    elif sev == 'Low':
                        lowc += 1

    try:
        commit_hash = subprocess.check_output(['git','rev-parse','--short','HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        commit_hash = 'unknown'

    version_dir = Path('reports') / 'history'
    version_dir.mkdir(parents=True, exist_ok=True)
    versions_index = version_dir / 'versions.json'
    versions = []
    if versions_index.exists():
        try:
            versions = json.loads(versions_index.read_text(encoding='utf-8'))
        except Exception:
            versions = []

    prev = versions[-1] if versions else None
    deltas_html = "<p>No previous version available for delta comparison.</p>"
    if prev:
        def fmt(v):
            return f"{v:.4f}" if isinstance(v,(int,float)) else 'N/A'
        def delta(new, old):
            if isinstance(new,(int,float)) and isinstance(old,(int,float)):
                return f"{new-old:+.4f}"
            return 'N/A'
        deltas_html = f"""
        <table style='border-collapse:collapse;'>
        <tr><th style='text-align:left;padding:4px;'>Metric</th><th style='text-align:left;padding:4px;'>Current</th><th style='text-align:left;padding:4px;'>Previous</th><th style='text-align:left;padding:4px;'>Delta</th></tr>
        <tr><td style='padding:4px;'>AUC</td><td style='padding:4px;'>{fmt(auc_val)}</td><td style='padding:4px;'>{fmt(prev.get('auc'))}</td><td style='padding:4px;'>{delta(auc_val, prev.get('auc'))}</td></tr>
        <tr><td style='padding:4px;'>ECE</td><td style='padding:4px;'>{fmt(ece_val)}</td><td style='padding:4px;'>{fmt(prev.get('ece'))}</td><td style='padding:4px;'>{delta(ece_val, prev.get('ece'))}</td></tr>
        <tr><td style='padding:4px;'>Drift</td><td style='padding:4px;'>{fmt(drift_val)}</td><td style='padding:4px;'>{fmt(prev.get('drift'))}</td><td style='padding:4px;'>{delta(drift_val, prev.get('drift'))}</td></tr>
        <tr><td style='padding:4px;'>High Incidents</td><td style='padding:4px;'>{high}</td><td style='padding:4px;'>{prev.get('incidents_high','N/A')}</td><td style='padding:4px;'>{delta(high, prev.get('incidents_high'))}</td></tr>
        <tr><td style='padding:4px;'>Medium Incidents</td><td style='padding:4px;'>{med}</td><td style='padding:4px;'>{prev.get('incidents_medium','N/A')}</td><td style='padding:4px;'>{delta(med, prev.get('incidents_medium'))}</td></tr>
        <tr><td style='padding:4px;'>Low Incidents</td><td style='padding:4px;'>{lowc}</td><td style='padding:4px;'>{prev.get('incidents_low','N/A')}</td><td style='padding:4px;'>{delta(lowc, prev.get('incidents_low'))}</td></tr>
        </table>
        """

    html_original = (BUILD / 'combined.html').read_text(encoding='utf-8')
    insertion_marker = "<div class='cover'>"
    change_section = f"""
    <div class='section'>
    <h2>Performance Change Log</h2>
    {deltas_html}
    </div>
    """
    if insertion_marker in html_original:
        parts = html_original.split(insertion_marker)
        html_modified = parts[0] + insertion_marker + change_section + parts[1]
    else:
        html_modified = change_section + html_original
    (BUILD / 'combined.html').write_text(html_modified, encoding='utf-8')

    entry = {
        'commit_hash': commit_hash,
        'generation_time_utc': ts,
        'auc': auc_val,
        'ece': ece_val,
        'drift': drift_val,
        'incidents_high': high,
        'incidents_medium': med,
        'incidents_low': lowc,
    }

    versions.append(entry)
    versions_index.write_text(json.dumps(versions, indent=2), encoding='utf-8')

    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    version_pdf_name = f"BioSignalX_Report_{date_str}_{commit_hash}.pdf"
    (BUILD / 'versioned_name.txt').write_text(version_pdf_name, encoding='utf-8')
    print('Version metadata updated ->', version_pdf_name)

if __name__ == '__main__':
    main()
