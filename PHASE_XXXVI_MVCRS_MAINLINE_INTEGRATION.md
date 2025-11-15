# Phase XXXVI — MV-CRS Mainline Integration & Governance Chain Binding

**Phase**: XXXVI  
**Date**: 2025-11-15  
**Status**: ✅ Complete  
**Version**: v2.11.0-mvcrs-integration

---

## Overview

Phase XXXVI completes the Multi-Verifier Challenge-Response System (MV-CRS) by integrating all phases with upstream governance chains into a unified decision framework. The integration orchestrator synthesizes signals from verifier, correction, escalation, lifecycle, policy fusion, thresholds, RDGL, and trust lock into a final decision: **allow**, **restricted**, or **blocked**.

**Key Achievement**: Closed-loop governance with unified decision framework binding MV-CRS phases and upstream governance into a single integration status with live portal visibility.

---

## Purpose of Integration

### Problem Statement
Prior to Phase XXXVI, MV-CRS phases operated autonomously without a unified decision framework. Upstream governance states (policy fusion, trust lock, RDGL) were not synthesized with MV-CRS outputs (verifier, correction, escalation, lifecycle) to produce actionable decisions.

### Solution
The **Integration Orchestrator** loads all MV-CRS and governance states, applies a decision matrix, and produces a synthesized integration status with a clear final decision that gates system actions.

### Use Cases
- **Deployment Gates**: Block deployments when `final_decision = blocked`
- **Alerting**: Trigger alerts when `final_decision = restricted` for >24h
- **Audit Trails**: Maintain append-only log of integration decisions
- **Portal Visibility**: Live dashboard card showing current integration status

---

## Decision Matrix

### Final Decision Logic

| Decision | Conditions | Meaning |
|----------|-----------|---------|
| **allow** | ✅ MV-CRS core OK<br>✅ No escalations open<br>✅ Governance green<br>✅ Lifecycle resolved/rejected | All systems healthy, operations permitted |
| **restricted** | ⚠️ Escalation open<br>⚠️ Governance yellow<br>⚠️ Lifecycle pending/in_progress/awaiting_validation | Caution required, limited operations |
| **blocked** | ❌ Governance red + MV-CRS core not OK<br>❌ Lifecycle rejected<br>❌ Critical failures | Critical state, operations blocked |

### Decision Precedence
1. **Blocked** (highest priority): Governance red + MV-CRS not OK → immediate block
2. **Restricted**: Escalation open OR governance yellow OR active lifecycle
3. **Allow** (default healthy): All signals green, no escalations, lifecycle resolved

---

## Implementation Details

### Engine: `scripts/mvcrs/mvcrs_integration_orchestrator.py`

**Responsibilities**:
- Load MV-CRS states (verifier, correction, escalation, lifecycle)
- Load governance states (policy fusion, thresholds, RDGL, trust lock)
- Analyze `mvcrs_core_ok` based on verifier status and correction blocks
- Detect `escalation_open` from lifecycle state
- Derive `governance_risk_level` (green/yellow/red) from upstream signals
- Compute `final_decision` using decision matrix
- Write integration state and log
- Update audit marker

**Inputs**:
- `state/challenge_verifier_state.json` (verifier results)
- `state/mvcrs_last_correction.json` (correction engine output)
- `state/mvcrs_escalation.json` (escalation artifact)
- `state/mvcrs_escalation_lifecycle.json` (lifecycle state)
- `state/policy_fusion_state.json` (policy fusion GREEN/YELLOW/RED)
- `state/threshold_policy.json` (adaptive thresholds)
- `state/rdgl_policy_adjustments.json` (RDGL mode)
- `state/trust_lock_state.json` (trust lock status)

**Outputs**:
- `state/mvcrs_integration_state.json` (synthesized status)
- `logs/mvcrs_integration_log.jsonl` (append-only audit trail)
- `docs/audit_summary.md` (idempotent markers: `<!-- MVCRS_INTEGRATION: UPDATED|FAILED|VERIFIED <UTC> -->`)

**Key Functions**:
```python
analyze_mvcrs_core_ok(mvcrs_states) -> bool
analyze_escalation_open(mvcrs_states) -> bool
get_lifecycle_state(mvcrs_states) -> str
analyze_governance_risk_level(gov_states) -> str  # green/yellow/red
compute_final_decision(mvcrs_core_ok, escalation_open, lifecycle_state, governance_risk) -> str
build_integration_state(mvcrs_states, gov_states) -> dict
write_integration_state(state) -> bool
append_integration_log(entry) -> bool
update_audit_marker(status) -> bool
```

### Integration State Schema

```json
{
  "timestamp": "2025-11-15T00:00:00Z",
  "mvcrs_core_ok": true,
  "escalation_open": false,
  "lifecycle_state": "resolved",
  "governance_risk_level": "green",
  "final_decision": "allow",
  "inputs": {
    "verifier_status": "ok",
    "correction_type": "none",
    "lifecycle_resolved_count": 5,
    "lifecycle_rejected_count": 1,
    "policy_fusion_state": "FUSION_GREEN",
    "trust_locked": false,
    "rdgl_mode": "adaptive"
  }
}
```

---

## CI Workflow Chain

### Full MV-CRS CI Orchestration

```
03:30 UTC → mvcrs_challenge.yml (verifier)
              ↓ (on completion)
         mvcrs_correction.yml (correction engine)
              ↓
06:40 UTC → mvcrs_escalation_lifecycle.yml (lifecycle orchestration)
              ↓
06:50 UTC → mvcrs_integration.yml (integration orchestrator)
              ↓
         Portal updates (15s refresh)
```

### Workflow: `.github/workflows/mvcrs_integration.yml`

**Trigger**:
- Daily at 06:50 UTC (after lifecycle workflow at 06:40)
- Manual dispatch with `force_fix_branch` input

**Steps**:
1. Checkout repository
2. Set up Python 3.11
3. Install pytest
4. **Check failure conditions**:
   - Lifecycle stuck in `pending`/`in_progress` for >48h
   - Escalation open for >72h
5. Run integration orchestrator
6. Upload integration artifacts (90-day retention)
7. **Fail workflow if**:
   - Lifecycle stuck >48h
   - Escalation open >72h
   - Governance risk = red AND mvcrs_core_ok = false
8. **On success**: Append `<!-- MVCRS_INTEGRATION: VERIFIED <UTC> -->`
9. **On failure**: Create fix branch `fix/mvcrs-integration-<timestamp>`, append `<!-- MVCRS_INTEGRATION: FAILED <UTC> -->`

**Failure Handling**:
- Creates fix branch with diagnostics: integration state + log + audit marker
- Pushes branch to remote for investigation
- Fails CI to block further automation until resolved

---

## Portal Integration

### Card: "MV-CRS Integration Status"

**Location**: `portal/index.html` (after Escalation Lifecycle card)

**Fields**:
- **Final Decision**: ALLOW / RESTRICTED / BLOCKED (large text)
- **Lifecycle State**: Current lifecycle stage
- **Escalation Open**: Yes / No
- **Governance Risk**: GREEN / YELLOW / RED
- **Last Updated**: ISO 8601 timestamp

**Badge Colors**:
- `allow`: Green (`status-green`)
- `restricted`: Orange (`#f59e0b`)
- `blocked`: Red (`#ef4444`)
- `unknown`: Gray (`#6b7280`)

**Auto-Refresh**: Every 15 seconds

**Implementation**:
```javascript
async function loadIntegrationStatus(){
    const resp = await fetch('../state/mvcrs_integration_state.json', {cache:'no-store'});
    const data = await resp.json();
    // Update DOM with final_decision, lifecycle_state, escalation_open, governance_risk_level
    // Set badge color based on final_decision
}
loadIntegrationStatus();
setInterval(loadIntegrationStatus, 15000);
```

---

## Safety Model

### Rate Limiting
- **Implicit**: Integration orchestrator runs daily (06:50 UTC)
- **No explicit limit**: Deterministic synthesis based on input states
- **Failure Detection**: Stuck escalations (>72h) or lifecycle (>48h) trigger CI failure

### Atomic Writes
- **Mechanism**: Write to `.tmp` file, then atomic rename
- **Retry**: 1s, 3s, 9s delays on failure
- **Fallback**: Create fix branch if all retries fail

### Fix-Branch Creation
- **Trigger**: Persistent file system errors after 3 retry attempts
- **Branch Name**: `fix/mvcrs-integration-<timestamp>`
- **Contents**: Integration state, log, audit marker diagnostics
- **Action**: Commits diagnostic state, pushes to remote

### Idempotent Audit Markers
- **Patterns**:
  - `<!-- MVCRS_INTEGRATION: UPDATED <UTC> -->` (normal operation)
  - `<!-- MVCRS_INTEGRATION: VERIFIED <UTC> -->` (CI success)
  - `<!-- MVCRS_INTEGRATION: FAILED <UTC> -->` (CI failure)
- **Behavior**: Remove existing markers before appending new one
- **Guarantee**: Exactly one marker per run type

### MVCRS_BASE_DIR Virtualization
- **Purpose**: Test isolation
- **Behavior**: All file paths resolve relative to `MVCRS_BASE_DIR` if set
- **Default**: Project root if environment variable not set

---

## Test Suite

### File: `tests/mvcrs/test_integration_orchestrator.py`

**Coverage**: 6 comprehensive tests

1. **test_all_healthy_signals_allow_decision**
   - All systems green → `final_decision = allow`
   - Verifier OK, lifecycle resolved, policy fusion green
   - Asserts: `mvcrs_core_ok=True`, `escalation_open=False`, `governance_risk_level=green`

2. **test_escalation_open_restricted_decision**
   - Escalation open → `final_decision = restricted`
   - Lifecycle in `awaiting_validation` state
   - Asserts: `escalation_open=True`, `final_decision=restricted`

3. **test_governance_red_mvcrs_not_ok_blocked**
   - Governance red + MV-CRS failed → `final_decision = blocked`
   - Verifier failed, policy fusion RED
   - Asserts: `mvcrs_core_ok=False`, `governance_risk_level=red`, `final_decision=blocked`

4. **test_lifecycle_stuck_detection**
   - Lifecycle stuck in `pending` for >48h
   - Verifies elapsed time calculation
   - Simulates CI failure condition

5. **test_idempotent_audit_marker**
   - Runs orchestrator twice
   - Verifies exactly one audit marker
   - Confirms UPDATED marker present

6. **test_fix_branch_on_persistent_write_failure**
   - Simulates write failure via monkeypatch
   - Verifies exit code = 2 (critical failure)
   - Tests error handling path

**Test Isolation**: Uses `lifecycle_sandbox` fixture for isolated temp directory with auto-cleanup

---

## Validation Instructions

### Local Dry-Run

```bash
# Set up environment
export MVCRS_BASE_DIR=/tmp/mvcrs_test
mkdir -p $MVCRS_BASE_DIR/{state,logs,docs}

# Create healthy verifier state
cat > $MVCRS_BASE_DIR/state/challenge_verifier_state.json <<EOF
{
  "timestamp": "2025-11-15T00:00:00Z",
  "status": "ok",
  "deviations": []
}
EOF

# Create resolved lifecycle
cat > $MVCRS_BASE_DIR/state/mvcrs_escalation_lifecycle.json <<EOF
{
  "timestamp": "2025-11-15T00:00:00Z",
  "current_state": "resolved",
  "entered_current_state_at": "2025-11-15T00:00:00Z",
  "last_transition_reason": "Validation passed",
  "resolved_count": 5,
  "rejected_count": 1
}
EOF

# Create green policy fusion
cat > $MVCRS_BASE_DIR/state/policy_fusion_state.json <<EOF
{
  "timestamp": "2025-11-15T00:00:00Z",
  "fusion_state": "FUSION_GREEN"
}
EOF

# Run integration orchestrator
python scripts/mvcrs/mvcrs_integration_orchestrator.py

# Inspect outputs
cat $MVCRS_BASE_DIR/state/mvcrs_integration_state.json
cat $MVCRS_BASE_DIR/logs/mvcrs_integration_log.jsonl
grep "MVCRS_INTEGRATION" $MVCRS_BASE_DIR/docs/audit_summary.md

# Expected: final_decision = "allow"
```

### Test Suite Execution

```bash
# Run integration tests
pytest tests/mvcrs/test_integration_orchestrator.py -v

# Run full MV-CRS suite
pytest tests/mvcrs tests/mvcrs_correction -v

# Expected: All tests pass (52 total: 46 prior + 6 integration)
```

### CI Workflow Trigger

```bash
# Manual dispatch (GitHub Actions)
# Navigate to: Actions → MVCRS Integration Orchestrator → Run workflow
# Optional: Enable "force_fix_branch" to test failure path

# Check artifacts after run:
# - mvcrs-integration-artifacts.zip contains:
#   - state/mvcrs_integration_state.json
#   - logs/mvcrs_integration_log.jsonl
#   - docs/audit_summary.md
```

### Portal Verification

1. Open `portal/index.html` in browser
2. Locate "MV-CRS Integration Status" card (after Escalation Lifecycle)
3. Verify fields populate from `state/mvcrs_integration_state.json`
4. Check badge color matches final decision:
   - Green = Allow
   - Orange = Restricted
   - Red = Blocked
5. Confirm auto-refresh every 15 seconds

---

## Integration with Existing Components

### Verifier → Integration
- **Output**: `state/challenge_verifier_state.json` with `status: ok|warning|failed`
- **Input to Integration**: Determines `mvcrs_core_ok`

### Correction → Integration
- **Output**: `state/mvcrs_last_correction.json` with `correction_type` and block flags
- **Input to Integration**: Affects `mvcrs_core_ok` (blocks reduce score)

### Lifecycle → Integration
- **Output**: `state/mvcrs_escalation_lifecycle.json` with `current_state`
- **Input to Integration**: Determines `escalation_open` and `lifecycle_state`

### Policy Fusion → Integration
- **Output**: `state/policy_fusion_state.json` with `fusion_state: FUSION_GREEN|YELLOW|RED`
- **Input to Integration**: Primary driver of `governance_risk_level`

### Trust Lock → Integration
- **Output**: `state/trust_lock_state.json` with `locked: true|false`
- **Input to Integration**: Escalates governance risk to red when locked

### RDGL → Integration
- **Output**: `state/rdgl_policy_adjustments.json` with `mode: relaxed|normal|tightening|locked`
- **Input to Integration**: Affects governance risk level

### Portal Display
- **Input**: `state/mvcrs_integration_state.json` with all synthesized fields
- **Output**: Live dashboard card with 15s auto-refresh

---

## Artifacts Reference

| Artifact | Path | Format | Purpose |
|----------|------|--------|---------|
| Integration State | `state/mvcrs_integration_state.json` | JSON | Synthesized decision + inputs |
| Integration Log | `logs/mvcrs_integration_log.jsonl` | JSONL | Append-only audit trail |
| Audit Markers | `docs/audit_summary.md` | Markdown | Idempotent UPDATED/VERIFIED/FAILED markers |
| CI Workflow | `.github/workflows/mvcrs_integration.yml` | YAML | Daily orchestration + failure detection |
| Engine Script | `scripts/mvcrs/mvcrs_integration_orchestrator.py` | Python | Decision logic + I/O |
| Test Suite | `tests/mvcrs/test_integration_orchestrator.py` | Python | 6 comprehensive tests |
| Portal Card | `portal/index.html` | HTML+JS | Live dashboard card with 15s refresh |

---

## Success Metrics

- ✅ **Decision Matrix**: Allow/restricted/blocked logic implemented
- ✅ **Signal Synthesis**: All MV-CRS + governance states integrated
- ✅ **CI Integration**: Daily workflow with failure detection (>48h lifecycle, >72h escalation)
- ✅ **Portal Card**: Live status with final decision and risk indicators
- ✅ **Test Coverage**: 6/6 tests passing (52/52 total MV-CRS suite)
- ✅ **Safety**: Atomic writes, idempotent markers, fix-branch creation
- ✅ **Audit Trail**: JSONL log + markdown markers (UPDATED/VERIFIED/FAILED)

---

## Future Enhancements

1. **Decision API**: REST endpoint to query integration status
2. **Webhook Integration**: POST decision changes to external systems
3. **Conditional Branching**: Deploy pipeline gates based on `final_decision`
4. **Historical Analytics**: Trend analysis of decision distributions
5. **Manual Override**: Admin API to force `final_decision` with audit trail
6. **Slack/Email Alerts**: Notifications on decision state changes

---

## Conclusion

Phase XXXVI delivers a production-ready integration orchestrator that synthesizes all MV-CRS phases and upstream governance chains into a unified decision framework. The deterministic decision matrix, combined with daily CI orchestration and live portal visibility, provides autonomous yet transparent governance integration with clear actionable outcomes.

**Completion**: Full MV-CRS system (Phases XXX-XXXVI) integrated into mainline governance with closed-loop decision framework.

---

**Completion Date**: 2025-11-15  
**Committed By**: Copilot Agent (Autonomous Implementation)  
**Tag**: `v2.11.0-mvcrs-integration`
