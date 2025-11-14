# Phase XXXV — MV-CRS Escalation Lifecycle Orchestration

**Phase**: XXXV  
**Date**: 2025-11-15  
**Status**: ✅ Complete  
**Version**: v2.10.0-mvcrs-escalation-lifecycle

---

## Overview

Phase XXXV completes the Multi-Verifier Challenge-Response System (MV-CRS) by implementing a deterministic state machine for escalation lifecycle management. The lifecycle engine orchestrates the complete journey from escalation detection through correction, validation, and resolution.

**Key Achievement**: Closed-loop governance with autonomous escalation lifecycle management, bridging verifier detection, correction engine application, and validation outcomes.

---

## State Machine Architecture

### Lifecycle States

```
pending
   ↓  (>24h elapsed)
in_progress
   ↓  (correction artifact detected)
corrective_action_applied
   ↓  (validation triggered)
awaiting_validation
   ↓
   ├─→ resolved (verifier status = ok)
   └─→ rejected (verifier status = failed/warning)
```

**Terminal States**: `resolved`, `rejected` (no further transitions)

### State Definitions

| State | Description | Entry Condition | Exit Condition |
|-------|-------------|----------------|----------------|
| `pending` | Escalation created, awaiting human/system review | Verifier status = failed | >24h elapsed |
| `in_progress` | Active investigation/correction in progress | Pending >24h | Correction artifact appears |
| `corrective_action_applied` | Correction engine has applied fixes | Correction detected | Awaiting validation run |
| `awaiting_validation` | Validation run pending/in-progress | Post-correction | Verifier re-run complete |
| `resolved` | Escalation successfully resolved | Verifier status = ok | Terminal |
| `rejected` | Correction failed to resolve issue | Verifier still failing | Terminal |

---

## Transition Rules

### Auto-Transition Logic

1. **Escalation Creation** (`None → pending`)
   - **Trigger**: Verifier reports `status: failed`
   - **Condition**: No existing escalation artifact
   - **Action**: Create `mvcrs_escalation_lifecycle.json` with state `pending`

2. **Escalation** (`pending → in_progress`)
   - **Trigger**: Time threshold exceeded
   - **Condition**: `elapsed_time > 24 hours` since entering `pending`
   - **Action**: Transition to `in_progress` with reason "Pending >24h"

3. **Correction Detection** (`in_progress → awaiting_validation`)
   - **Trigger**: Correction engine artifact detected
   - **Condition**: `mvcrs_last_correction.json` exists with `correction_type` = `soft` or `hard`
   - **Action**: Transition to `awaiting_validation` with reason "Correction artifact detected"

4. **Validation Success** (`awaiting_validation → resolved`)
   - **Trigger**: Verifier re-run shows success
   - **Condition**: Verifier `status: ok`
   - **Action**: Transition to `resolved`, increment `resolved_count`

5. **Validation Failure** (`awaiting_validation → rejected`)
   - **Trigger**: Verifier re-run shows continued failure
   - **Condition**: Verifier `status: failed` or `warning`
   - **Action**: Transition to `rejected`, increment `rejected_count`

### Manual Intervention Points

- **Pending >24h**: Human can acknowledge and approve transition to `in_progress`
- **Awaiting Validation**: Human can trigger manual validation run
- **Rejected**: Human can reset to `pending` for retry with different correction strategy

---

## Implementation Details

### Engine: `scripts/mvcrs/mvcrs_escalation_lifecycle.py`

**Responsibilities**:
- Load verifier state, correction state, escalation artifact, and previous lifecycle state
- Compute next state based on transition rules
- Build new lifecycle state JSON with counters and timestamps
- Write lifecycle state, append log entry, update audit marker

**Inputs**:
- `state/challenge_verifier_state.json` (verifier results)
- `state/mvcrs_last_correction.json` (correction engine output)
- `state/mvcrs_escalation.json` (escalation artifact)
- `state/mvcrs_escalation_lifecycle.json` (previous lifecycle state)

**Outputs**:
- `state/mvcrs_escalation_lifecycle.json` (current lifecycle state)
- `state/mvcrs_escalation_lifecycle_log.jsonl` (append-only audit trail)
- `docs/audit_summary.md` (idempotent marker `<!-- MVCRS_ESCALATION_LIFECYCLE: UPDATED <UTC> -->`)

**Key Functions**:
```python
compute_next_state(lifecycle, verifier_state, correction_state, escalation) -> (next_state, reason)
should_create_escalation(verifier_state, escalation) -> bool
should_transition_to_in_progress(lifecycle) -> bool
should_transition_to_awaiting_validation(lifecycle, correction_state) -> bool
should_transition_to_resolved(lifecycle, verifier_state) -> bool
should_transition_to_rejected(lifecycle, verifier_state) -> bool
build_lifecycle_state(...) -> dict
write_lifecycle_state(state) -> bool
append_lifecycle_log(entry) -> bool
update_audit_marker() -> bool
```

### CI Workflow: `.github/workflows/mvcrs_escalation_lifecycle.yml`

**Trigger**:
- Daily at 06:40 UTC (after correction workflow at 06:20)
- Manual dispatch with `force_fix_branch` input

**Steps**:
1. Checkout repository
2. Set up Python 3.11
3. Install pytest
4. Check consecutive failure count (stuck >3 days)
5. Run escalation lifecycle engine
6. Upload lifecycle artifacts (90-day retention)
7. Fail workflow if stuck >3 days
8. Create fix branch on persistent failure: `fix/mvcrs-escalation-lifecycle-<timestamp>`

**Failure Handling**:
- If lifecycle stuck in non-terminal state for >72 hours → workflow fails
- Creates fix branch with diagnostics: lifecycle state + log + audit marker
- Appends `<!-- MVCRS_ESCALATION_LIFECYCLE: FAILED <UTC> -->` to audit summary

---

## Portal Integration

### Card: "Escalation Lifecycle"

**Location**: `portal/index.html` (after Correction Engine Status card)

**Fields**:
- **Current Stage**: State name (e.g., "PENDING", "AWAITING VALIDATION", "RESOLVED")
- **Time in Stage**: Human-readable duration (e.g., "2d 4h" or "8h")
- **Last Transition**: ISO 8601 timestamp of last state change
- **Resolved Count**: Total escalations resolved since inception
- **Rejected Count**: Total escalations rejected since inception

**Badge Colors**:
- `resolved`: Green (`status-green`)
- `rejected`: Red (`#ef4444`)
- `pending`: Orange (`#f59e0b`)
- `awaiting_validation`: Blue (`status-certified`)
- Other states: Gray (`#6b7280`)

**Auto-Refresh**: Every 15 seconds

**Implementation**:
```javascript
async function loadLifecycleStatus(){
    const resp = await fetch('../state/mvcrs_escalation_lifecycle.json', {cache:'no-store'});
    const data = await resp.json();
    // Compute time in stage from entered_current_state_at
    // Update DOM elements with state, counters, timestamps
    // Set badge color based on state
}
loadLifecycleStatus();
setInterval(loadLifecycleStatus, 15000);
```

---

## Safety Model

### Rate Limiting
- **Implicit**: Lifecycle engine runs daily (06:40 UTC)
- **No hard limit**: State machine is deterministic; transitions occur based on conditions, not frequency
- **Stuck Detection**: >72h in non-terminal state triggers workflow failure

### Fix-Branch Creation
- **Trigger**: Persistent file system errors after 3 retry attempts (1s/3s/9s delays)
- **Branch Name**: `fix/mvcrs-escalation-lifecycle-<timestamp>`
- **Contents**: Lifecycle state, log, audit marker diagnostics
- **Action**: Commits diagnostic state, pushes to remote

### Atomic Writes
- **Mechanism**: Write to `.tmp` file, then atomic rename
- **Retry**: 1s, 3s, 9s delays on failure
- **Fallback**: Create fix branch if all retries fail

### Idempotent Audit Markers
- **Pattern**: `<!-- MVCRS_ESCALATION_LIFECYCLE: UPDATED <UTC> -->`
- **Behavior**: Remove existing marker before appending new one
- **Guarantee**: Exactly one marker per run, regardless of multiple executions

### MVCRS_BASE_DIR Virtualization
- **Purpose**: Test isolation
- **Behavior**: All file paths resolve relative to `MVCRS_BASE_DIR` if set
- **Default**: Project root if environment variable not set

---

## Test Suite

### File: `tests/mvcrs/test_escalation_lifecycle.py`

**Coverage**: 6 comprehensive tests

1. **test_escalation_auto_creates_on_verifier_failure**
   - Verifies escalation is created with `pending` state when verifier fails
   - Asserts lifecycle state JSON is written with correct status

2. **test_pending_to_in_progress_after_24h**
   - Validates 24-hour threshold for pending → in_progress transition
   - Tests time-based transition logic with mocked timestamps

3. **test_correction_artifact_triggers_awaiting_validation**
   - Confirms correction artifact detection triggers state change
   - Tests `should_transition_to_awaiting_validation` logic

4. **test_validation_success_resolves_escalation**
   - Verifies that verifier `status: ok` resolves escalation
   - Asserts `resolved_count` increments correctly

5. **test_validation_fail_rejects_escalation**
   - Confirms that verifier still failing after correction rejects escalation
   - Asserts `rejected_count` increments correctly

6. **test_idempotent_audit_marker_and_atomic_writes**
   - Runs lifecycle engine twice
   - Verifies exactly one audit marker despite multiple runs
   - Validates JSON structure of lifecycle state and log entries

**Test Isolation**: Uses `lifecycle_sandbox` fixture for isolated temp directory with auto-cleanup

---

## Validation Instructions

### Local Dry-Run

```bash
# Set up environment
export MVCRS_BASE_DIR=/tmp/mvcrs_test
mkdir -p $MVCRS_BASE_DIR/{state,docs}

# Create failed verifier state
cat > $MVCRS_BASE_DIR/state/challenge_verifier_state.json <<EOF
{
  "timestamp": "2025-11-15T00:00:00Z",
  "status": "failed",
  "deviations": [{"type": "TYPE_A_STRUCTURE", "severity": "high"}]
}
EOF

# Run lifecycle engine
python scripts/mvcrs/mvcrs_escalation_lifecycle.py

# Inspect outputs
cat $MVCRS_BASE_DIR/state/mvcrs_escalation_lifecycle.json
cat $MVCRS_BASE_DIR/state/mvcrs_escalation_lifecycle_log.jsonl
grep "MVCRS_ESCALATION_LIFECYCLE" $MVCRS_BASE_DIR/docs/audit_summary.md
```

### Test Suite Execution

```bash
# Run lifecycle tests
pytest tests/mvcrs/test_escalation_lifecycle.py -v

# Run full MV-CRS suite
pytest tests/mvcrs tests/mvcrs_correction -v

# Expected: All tests pass
```

### CI Workflow Trigger

```bash
# Manual dispatch (GitHub Actions)
# Navigate to: Actions → MVCRS Escalation Lifecycle → Run workflow
# Optional: Enable "force_fix_branch" to test failure path

# Check artifacts after run:
# - mvcrs-lifecycle-artifacts.zip contains:
#   - state/mvcrs_escalation_lifecycle.json
#   - state/mvcrs_escalation_lifecycle_log.jsonl
#   - docs/audit_summary.md
```

### Portal Verification

1. Open `portal/index.html` in browser
2. Locate "Escalation Lifecycle" card (after Correction Engine Status)
3. Verify fields populate from `state/mvcrs_escalation_lifecycle.json`
4. Check badge color matches current state
5. Confirm auto-refresh every 15 seconds

---

## Integration with Existing MV-CRS Components

### Verifier → Lifecycle
- **Output**: `state/challenge_verifier_state.json` with `status: failed`
- **Input to Lifecycle**: Triggers escalation creation (`None → pending`)

### Correction → Lifecycle
- **Output**: `state/mvcrs_last_correction.json` with `correction_type: soft|hard`
- **Input to Lifecycle**: Triggers transition to `awaiting_validation`

### Lifecycle → Portal
- **Output**: `state/mvcrs_escalation_lifecycle.json` with current state + counters
- **Display**: Portal card with auto-refresh, badge colors, time-in-stage calculation

### CI Orchestration Chain
```
mvcrs_challenge.yml (03:30 UTC)
   → verifier runs
   → escalation artifact created if failed
      ↓
mvcrs_correction.yml (after verifier completion)
   → correction engine runs on failed/warning
   → correction artifact written
      ↓
mvcrs_escalation_lifecycle.yml (06:40 UTC)
   → lifecycle engine runs
   → state transitions computed
   → lifecycle state + log updated
```

---

## Artifacts Reference

| Artifact | Path | Format | Purpose |
|----------|------|--------|---------|
| Lifecycle State | `state/mvcrs_escalation_lifecycle.json` | JSON | Current lifecycle state snapshot |
| Lifecycle Log | `state/mvcrs_escalation_lifecycle_log.jsonl` | JSONL | Append-only audit trail of transitions |
| Audit Marker | `docs/audit_summary.md` | Markdown | Idempotent timestamp marker |
| CI Workflow | `.github/workflows/mvcrs_escalation_lifecycle.yml` | YAML | Daily orchestration + failure handling |
| Engine Script | `scripts/mvcrs/mvcrs_escalation_lifecycle.py` | Python | State machine logic + I/O |
| Test Suite | `tests/mvcrs/test_escalation_lifecycle.py` | Python | 6 comprehensive tests |
| Portal Card | `portal/index.html` | HTML+JS | Live dashboard card with 15s refresh |

---

## Success Metrics

- ✅ **State Machine**: Deterministic transitions implemented
- ✅ **Auto-Transitions**: 24h threshold, correction detection, validation outcomes
- ✅ **CI Integration**: Daily workflow with stuck detection (>72h)
- ✅ **Portal Card**: Live status with time-in-stage and counters
- ✅ **Test Coverage**: 6/6 tests passing
- ✅ **Safety**: Atomic writes, idempotent markers, fix-branch creation
- ✅ **Audit Trail**: JSONL log + markdown marker

---

## Future Enhancements

1. **Manual Override API**: REST endpoint to force state transitions
2. **Retry Logic**: Auto-retry rejected escalations with exponential backoff
3. **Notification Hooks**: Slack/email alerts on state transitions
4. **Metrics Aggregation**: Weekly/monthly resolved vs rejected trends
5. **State History Visualization**: Timeline chart in portal
6. **Conditional Transitions**: Policy-based rules for transition gating

---

## Conclusion

Phase XXXV delivers a production-ready escalation lifecycle orchestration system, completing the MV-CRS governance loop. The deterministic state machine, combined with daily CI orchestration and live portal visibility, provides autonomous yet transparent escalation management with human oversight points at critical junctions.

**Next Phase**: MV-CRS mainline integration and v2.10.0 release tagging.

---

**Completion Date**: 2025-11-15  
**Committed By**: Copilot Agent (Autonomous Implementation)  
**Tag**: `v2.10.0-mvcrs-escalation-lifecycle`
