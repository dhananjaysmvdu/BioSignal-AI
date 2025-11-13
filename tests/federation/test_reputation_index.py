import json
import importlib
from pathlib import Path

mod = importlib.import_module('scripts.federation.reputation_index_engine')


def test_reputation_scoring_math(monkeypatch, tmp_path):
    # Peer config
    peers = [
        {'name':'peerA','base_url':'https://peerA'},
        {'name':'peerB','base_url':'https://peerB'},
    ]
    fed = tmp_path / 'federation'
    fed.mkdir(parents=True, exist_ok=True)
    (fed / 'peers.json').write_text(json.dumps(peers), encoding='utf-8')

    # Monkeypatch ROOT/FED
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    monkeypatch.setattr(mod, 'FED', fed)

    # Fake fetches
    def fake_http_get_json(url: str, timeout: int = 10):
        if url.endswith('provenance_consensus.json'):
            return {'agreement_pct': 95.0}
        if url.endswith('trust_consensus_report.json'):
            return {'trust': {'status':'verified'}}
        if url.endswith('fairness_summary.json'):
            return {'fairness_min_pct': 98.0}
        return None

    driftA = [
        {'agreement_pct': 88.0},
        {'agreement_pct': 92.0},
        {'agreement_pct': 100.0},
        {'agreement_pct': 99.0},
    ]
    driftB = [
        {'agreement_pct': 70.0},
        {'agreement_pct': 85.0},
        {'agreement_pct': 60.0},
        {'agreement_pct': 50.0},
        {'agreement_pct': 40.0},
    ]

    def fake_http_get_text(url: str, timeout: int = 10):
        if url.startswith('https://peerA') and url.endswith('provenance_drift_log.jsonl'):
            return "\n".join(json.dumps(x) for x in driftA)
        if url.startswith('https://peerB') and url.endswith('provenance_drift_log.jsonl'):
            return "\n".join(json.dumps(x) for x in driftB)
        return None

    monkeypatch.setattr(mod, 'http_get_json', fake_http_get_json)
    monkeypatch.setattr(mod, 'http_get_text', fake_http_get_text)

    rc = mod.main()
    assert rc == 0
    out = json.loads((fed / 'reputation_index.json').read_text(encoding='utf-8'))
    assert 'scores' in out and len(out['scores']) == 2
    # Scores are clamped to [0,100]
    for s in out['scores']:
        assert 0.0 <= float(s['score']) <= 100.0
    # PeerA should outrank PeerB given higher agreements and ethics bonus
    assert out['scores'][0]['peer'] == 'peerA'
