#!/usr/bin/env python3
"""
UI tests for Policy Fusion Portal Integration

Tests:
- policy_fusion_state.json is fetchable
- Card renders expected fields
"""

import json
import pytest
from pathlib import Path


def test_fusion_state_file_structure():
    """Test: policy_fusion_state.json has expected structure"""
    fusion_state_path = Path("state/policy_fusion_state.json")
    
    # Skip if file doesn't exist (not yet generated)
    if not fusion_state_path.exists():
        pytest.skip("Fusion state file not yet generated")
    
    with fusion_state_path.open("r") as f:
        data = json.load(f)
    
    # Verify structure
    assert "fusion_level" in data
    assert data["fusion_level"] in ["FUSION_GREEN", "FUSION_YELLOW", "FUSION_RED"]
    assert "computed_at" in data
    assert "inputs" in data
    assert "reasons" in data
    
    # Verify inputs structure
    inputs = data["inputs"]
    assert "policy" in inputs
    assert "trust_locked" in inputs
    assert "weighted_consensus_pct" in inputs
    assert "safety_brake_engaged" in inputs


def test_fusion_portal_card_fields():
    """Test: Portal HTML contains fusion card with expected fields"""
    portal_path = Path("portal/index.html")
    
    assert portal_path.exists(), "Portal index.html not found"
    
    with portal_path.open("r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    
    # Verify fusion card exists
    assert "Policy Fusion Status" in content
    assert 'id="fusion-level"' in content
    assert 'id="fusion-badge"' in content
    assert 'id="fusion-consensus"' in content
    assert 'id="fusion-brake"' in content
    assert 'id="fusion-trust"' in content
    
    # Verify fetch path
    assert "../state/policy_fusion_state.json" in content
    
    # Verify auto-refresh JavaScript
    assert "loadPolicyFusionState" in content
    assert "setInterval(loadPolicyFusionState" in content
