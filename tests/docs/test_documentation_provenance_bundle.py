import json
import zipfile
from pathlib import Path
import importlib

SCRIPT = 'scripts.docs.build_doc_provenance_bundle'
mod = importlib.import_module(SCRIPT)
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
EXPORTS = ROOT / 'exports'


def test_bundle_contents_and_hash():
    # Build bundle
    mod.main()
    bundle = EXPORTS / 'documentation_provenance_bundle.zip'
    assert bundle.exists()

    with zipfile.ZipFile(bundle, 'r') as z:
        names = set(z.namelist())
    # Expected key files
    assert 'docs/readme_integrity.json' in names
    assert 'docs/transparency_integrity.json' in names
    assert 'INSTRUCTION_EXECUTION_SUMMARY.md' in names
    # At least one PHASE_*_COMPLETION_REPORT.md
    assert any(n.startswith('PHASE_') and n.endswith('_COMPLETION_REPORT.md') for n in names)

    # Hash consistency
    data = json.loads((DOCS / 'documentation_provenance_hash.json').read_text(encoding='utf-8'))
    recorded = data['sha256']

    # Compute local sha256
    import hashlib
    h = hashlib.sha256()
    with open(bundle, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    assert recorded == h.hexdigest()
