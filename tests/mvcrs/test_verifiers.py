import pytest
from scripts.mvcrs.verifier_primary import verify as v_primary
from scripts.mvcrs.verifier_secondary import verify as v_secondary
from scripts.mvcrs.verifier_tertiary import verify as v_tertiary

def test_verifier_stubs():
    ctx = {}
    assert v_primary(ctx)["method"] == "primary"
    assert v_secondary(ctx)["method"] == "secondary"
    assert v_tertiary(ctx)["method"] == "tertiary"
