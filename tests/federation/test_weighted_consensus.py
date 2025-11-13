import json
import importlib
from pathlib import Path

rep_mod = importlib.import_module('scripts.federation.reputation_index_engine')
wc_mod = importlib.import_module('scripts.federation.weighted_consensus_engine')


def test_weighted_majority_and_markers(monkeypatch, tmp_path):
    # Setup temp ROOT and federation dir
    fed = tmp_path / 'federation'
    fed.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(wc_mod, 'ROOT', tmp_path)
    monkeypatch.setattr(wc_mod, 'FED', fed)
    monkeypatch.setattr(rep_mod, 'ROOT', tmp_path)
    monkeypatch.setattr(rep_mod, 'FED', fed)

    # Peers
    peers = [
        {'name': 'A', 'base_url': 'https://A'},
        {'name': 'B', 'base_url': 'https://B'},
        {'name': 'C', 'base_url': 'https://C'},
    ]
    (fed / 'peers.json').write_text(json.dumps(peers), encoding='utf-8')

    # Reputation: weight A=90, B=10, C=0 (C ignored)
    reputation = {
        'timestamp': 't',
        'peers_scored': 3,
        'scores': [
            {'peer': 'A', 'base_url': 'https://A', 'score': 90.0},
            {'peer': 'B', 'base_url': 'https://B', 'score': 10.0},
            {'peer': 'C', 'base_url': 'https://C', 'score': 0.0},
        ]
    }
    (fed / 'reputation_index.json').write_text(json.dumps(reputation), encoding='utf-8')
    (fed / 'provenance_consensus.json').write_text(json.dumps({'agreement_pct': 80.0}), encoding='utf-8')

    # Mock peer values: majority by weight is hash X
    values = {
        'https://A': {'ledger': 'X', 'anchor': 'X', 'bundle': 'X'},
        'https://B': {'ledger': 'Y', 'anchor': 'Y', 'bundle': 'Y'},
        'https://C': {'ledger': 'Y', 'anchor': 'X', 'bundle': 'Y'},
    }

    def fake_get_json(url: str, timeout: int = 10):
        # Map url to base
        base = None
        for k in values:
            if url.startswith(k):
                base = k
                break
        if base is None:
            return None
        if url.endswith('ledger_snapshot_hash.json'):
            v = values[base]['ledger']
            return [{'sha256': v}]
        if url.endswith('anchor_chain.json'):
            v = values[base]['anchor']
            return [{'chain_hash': v}]
        if url.endswith('documentation_provenance_hash.json'):
            v = values[base]['bundle']
            return {'sha256': v}
        return None

    monkeypatch.setattr(wc_mod, 'http_get_json', fake_get_json)

    rc = wc_mod.main()
    assert rc == 0
    out = json.loads((fed / 'weighted_consensus.json').read_text(encoding='utf-8'))
    assert 'weighted_agreement_pct' in out
    # With weights 90 vs 10, winner should be ~90% across categories
    assert out['weighted_agreement_pct'] >= 80.0

    # Audit markers
    audit = (tmp_path / 'audit_summary.md').read_text(encoding='utf-8')
    assert '<!-- WEIGHTED_CONSENSUS: VERIFIED ' in audit
