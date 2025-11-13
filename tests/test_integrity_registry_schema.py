import sys
import subprocess
from pathlib import Path


SCRIPT = Path('scripts/workflow_utils/validate_integrity_registry_schema.py')


def run_validator(registry: Path, audit: Path) -> int:
    cmd = [sys.executable, str(SCRIPT), '--registry', str(registry), '--audit-summary', str(audit)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    # Expose outputs to help debugging locally
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    return res.returncode


def test_schema_validator_pass(tmp_path: Path):
    registry = tmp_path / 'integrity_metrics_registry.csv'
    audit = tmp_path / 'audit_summary.md'

    # Create canonical header and a single row
    header = 'timestamp,integrity_score,violations,warnings,health_score,rri,mpi,confidence,status'\
    
    registry.write_text(header + "\n" +
                        "2025-01-01T00:00:00Z,95.0,0,1,90.0,5.0,80.0,0.950,ok\n",
                        encoding='utf-8')

    rc = run_validator(registry, audit)
    assert rc == 0

    content = registry.read_text(encoding='utf-8')
    assert '\n# schema_hash:' in content

    audit_text = audit.read_text(encoding='utf-8')
    assert '<!-- INTEGRITY_REGISTRY_SCHEMA:BEGIN -->' in audit_text
    assert 'schema OK' in audit_text or 'schema OK' in audit_text.lower()


def test_schema_validator_fail(tmp_path: Path):
    registry = tmp_path / 'integrity_metrics_registry.csv'
    audit = tmp_path / 'audit_summary.md'

    # Alter header (missing status column)
    bad_header = 'timestamp,integrity_score,violations,warnings,health_score,rri,mpi,confidence'
    registry.write_text(bad_header + "\n", encoding='utf-8')

    rc = run_validator(registry, audit)
    assert rc == 1

    content = registry.read_text(encoding='utf-8')
    assert '\n# schema_hash:' in content

    audit_text = audit.read_text(encoding='utf-8')
    assert '<!-- INTEGRITY_REGISTRY_SCHEMA:BEGIN -->' in audit_text
    assert 'mismatch' in audit_text.lower()
