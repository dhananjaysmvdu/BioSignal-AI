import os
import tempfile
from scripts.mvcrs.challenge_utils import append_jsonl, compute_chain_hash

def test_chain_hash_deterministic(tmp_path):
    events = tmp_path / "events.jsonl"
    # Two records appended
    append_jsonl(str(events), {"id": 1, "level": "soft", "deviation": 0.02})
    append_jsonl(str(events), {"id": 2, "level": "material", "deviation": 0.18})
    h1 = compute_chain_hash(str(events))
    # Recompute should match
    h2 = compute_chain_hash(str(events))
    assert h1 == h2 and h1 != ""

def test_chain_hash_changes_on_append(tmp_path):
    events = tmp_path / "events.jsonl"
    append_jsonl(str(events), {"id": 1, "level": "soft"})
    h1 = compute_chain_hash(str(events))
    append_jsonl(str(events), {"id": 2, "level": "soft"})
    h2 = compute_chain_hash(str(events))
    assert h1 != h2
