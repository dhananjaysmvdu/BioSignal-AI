import json
from pathlib import Path
import importlib

sync_mod = importlib.import_module('scripts.federation.provenance_sync_engine')
drift_mod = importlib.import_module('scripts.federation.provenance_drift_detector')
bridge_mod = importlib.import_module('scripts.federation.consensus_trust_bridge')

ROOT = Path(__file__).resolve().parents[2]


def test_majority_and_drift_detection(monkeypatch, tmp_path):
    # Set ROOT to temp for modules that use global ROOT
    monkeypatch.setattr(sync_mod, 'ROOT', tmp_path)
    monkeypatch.setattr(sync_mod, 'SNAPSHOTS', tmp_path / 'snapshots')
    monkeypatch.setattr(sync_mod, 'MIRRORS', tmp_path / 'mirrors')
    monkeypatch.setattr(sync_mod, 'DOCS', tmp_path / 'docs')
    monkeypatch.setattr(sync_mod, 'FED', tmp_path / 'federation')

    # Prepare local hashes
    (tmp_path / 'snapshots').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'mirrors').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'docs').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'federation').mkdir(parents=True, exist_ok=True)

    (tmp_path / 'snapshots' / 'ledger_snapshot_hash.json').write_text(
        json.dumps([{'sha256':'L1'}]), encoding='utf-8')
    (tmp_path / 'mirrors' / 'anchor_chain.json').write_text(
        json.dumps([{'chain_hash':'A1'}]), encoding='utf-8')
    (tmp_path / 'docs' / 'documentation_provenance_hash.json').write_text(
        json.dumps({'sha256':'B1'}), encoding='utf-8')

    # Mock peers: 3 peers with ledger ['L1','L1','L2'], anchor ['A1','A2','A1'], bundle ['B1','B1','B1']
    peers = [{'base_url':'https://peer1'},{'base_url':'https://peer2'},{'base_url':'https://peer3'}]
    monkeypatch.setattr(sync_mod, 'read_peers', lambda: peers)

    peer_vals = [
        {'ledger':'L1','anchor':'A1','bundle':'B1'},
        {'ledger':'L1','anchor':'A2','bundle':'B1'},
        {'ledger':'L2','anchor':'A1','bundle':'B1'},
    ]

    def fake_fetch(peer):
        i = peers.index(peer)
        return peer_vals[i]
    monkeypatch.setattr(sync_mod, 'fetch_peer_hashes', fake_fetch)

    rc = sync_mod.main()
    assert rc == 0

    c = json.loads((tmp_path / 'federation' / 'provenance_consensus.json').read_text(encoding='utf-8'))
    # Consensus should be L1, A1, B1
    assert c['ledger_consensus_hash'] == 'L1'
    assert c['anchor_consensus_hash'] == 'A1'
    assert c['bundle_consensus_hash'] == 'B1'
    # Agreement pct: local+3 peers = 4 nodes, matches per type = 3/4=75% for ledger and anchor, 4/4=100% bundle => min=75%
    assert c['agreement_pct'] == 75.0

    # Now drift detection should log and not fail if >= 90 threshold is unmet (<90 => fail with code 2)
    monkeypatch.setattr(drift_mod, 'ROOT', tmp_path)
    monkeypatch.setattr(drift_mod, 'FED', tmp_path / 'federation')
    # Ensure argparse doesn't see pytest args
    monkeypatch.setenv('PYTHONPATH', str(tmp_path))
    monkeypatch.setattr('sys.argv', ['provenance_drift_detector.py'])
    rc2 = drift_mod.main()
    assert rc2 == 2  # since 75% < 90
    drift_log = (tmp_path / 'federation' / 'provenance_drift_log.jsonl').read_text(encoding='utf-8')
    assert 'agreement_pct' in drift_log

    # Trust bridge structure validation
    # Write a dummy trust report
    results = tmp_path / 'results'
    results.mkdir(parents=True, exist_ok=True)
    (results / 'trust_federation_report.json').write_text(json.dumps({'status':'verified','peers_checked':3}), encoding='utf-8')

    monkeypatch.setattr(bridge_mod, 'ROOT', tmp_path)
    monkeypatch.setattr(bridge_mod, 'FED', tmp_path / 'federation')
    monkeypatch.setattr(bridge_mod, 'RESULTS', results)
    rc3 = bridge_mod.main()
    assert rc3 == 0
    out = json.loads((tmp_path / 'federation' / 'trust_consensus_report.json').read_text(encoding='utf-8'))
    assert 'provenance' in out and 'trust' in out
    assert out['trust']['agreement_pct'] == 100.0
