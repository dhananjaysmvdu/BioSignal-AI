# Policy Automation Runbook

**Version**: 2.5.1-policy-auto  
**Last Updated**: 2025-11-14

## Overview

This runbook covers operational procedures for the autonomous Policy Orchestration and Response system.

---

## 1. Manual Workflow Triggers

### Trigger Policy Response Runner (GitHub Actions)

```bash
# Navigate to Actions → Policy Response Runner → Run workflow
# Input: auto_apply = false (dry-run) or true (apply real actions)
```

### Run Orchestrator Locally

```bash
python scripts/policy/policy_orchestrator.py --run
```

**Output**: `state/policy_state.json`, `state/policy_state_log.jsonl`

---

## 2. Dry-Run Mode (Default)

Previews actions without execution.

```bash
# YELLOW policy
python scripts/response/run_policy_responses.py --policy YELLOW

# RED policy
python scripts/response/run_policy_responses.py --policy RED
```

**Output**: `state/policy_response_preview.json`

### Inspect Preview

```bash
# Windows PowerShell
Get-Content state/policy_response_preview.json | ConvertFrom-Json | ConvertTo-Json -Depth 10

# Linux/Mac
cat state/policy_response_preview.json | jq .
```

---

## 3. Apply Mode (Real Actions)

Requires `--apply` flag or `POLICY_AUTO_APPLY=true` in CI.

```bash
# Local execution
python scripts/response/run_policy_responses.py --policy RED --apply
```

**Output**: `state/policy_response_log.jsonl`, `state/policy_response_undo_*.json`

### Safety Gates (Auto-Checked Before Execution)

1. **Trust Guard**: Must be unlocked (`trust_lock_state.json: locked=false`)
2. **Safety Brake**: Must be OFF (`forensics/safety_brake_state.json: is_engaged=false`)
3. **Rate Limit**: Response count < max_allowed (default: 10/24h)
4. **Manual Unlock Count**: < daily limit (default: 3/day)

**If any gate fails**: Execution blocked, report written to `reports/policy_response_blocked.json`.

---

## 4. Rollback Procedures

### Manual Undo Using Undo Files

1. **Locate undo file**:
   ```bash
   ls state/policy_response_undo_*.json
   ```

2. **Read undo instructions**:
   ```json
   {
     "response_id": "...",
     "action": "integrity_anchor_mirror",
     "executed_at": "2025-11-14T12:00:00+00:00",
     "undo_instruction": "Restore previous anchor_chain.json from mirrors/anchor_chain.json.backup"
   }
   ```

3. **Execute undo**:
   ```bash
   # Example: restore anchor chain
   cp mirrors/anchor_chain.json.backup mirrors/anchor_chain.json
   ```

4. **Verify**:
   ```bash
   python scripts/forensics/verify_cold_storage.py
   ```

---

## 5. Reset Safety Mechanisms

### Reset Safety Brake

```bash
# Edit forensics/safety_brake_state.json
{
  "is_engaged": false,
  "response_count_24h": 0,
  "max_allowed": 10,
  "last_reset": "2025-11-14T00:00:00+00:00"
}
```

### Reset Manual Unlock Counter

```bash
# Edit trust_lock_state.json
{
  "locked": false,
  "manual_unlocks_today": 0,
  "manual_unlocks_last_reset": "2025-11-14"
}
```

### Force Unlock Trust Guard

```bash
python scripts/trust/trust_guard_controller.py --force-unlock --reason "manual-override"
```

---

## 6. Policy Actions by Level

### YELLOW Policy (Soft Actions)

- Integrity schema check
- CSV schema validation
- **Duration**: ~30 seconds
- **Reversible**: No (read-only)

### RED Policy (Hard Actions)

- Full integrity check
- Cold storage verification
- Integrity anchor mirror regeneration
- **Duration**: ~2-5 minutes
- **Reversible**: Anchor regeneration only (undo file created)

---

## 7. Monitoring & Alerts

### Check Policy State

```bash
# Current policy
cat state/policy_state.json | jq '.policy'

# Policy history
cat state/policy_state_log.jsonl | tail -n 10
```

### Check Response Logs

```bash
# Dry-run preview
cat state/policy_response_preview.json | jq .

# Execution log
cat state/policy_response_log.jsonl | tail -n 5
```

### Check Blocked Reports

```bash
cat reports/policy_response_blocked.json | jq .
```

---

## 8. Troubleshooting

### Issue: Policy stuck at RED

**Diagnosis**:
```bash
python scripts/policy/policy_orchestrator.py --run | jq '.inputs'
```

**Resolution**:
- If `forecast_risk=high`: Wait for forecast update (daily 03:00 UTC)
- If `recent_responses>=8`: Reset safety brake
- If `integrity_score<90%`: Run integrity checks and fix violations

### Issue: Response blocked by trust guard

**Diagnosis**:
```bash
cat trust_lock_state.json | jq '.locked, .reason'
```

**Resolution**:
```bash
python scripts/trust/trust_guard_controller.py --force-unlock --reason "manual-investigation-complete"
```

### Issue: Fix branch created

**Diagnosis**:
```bash
git branch --list 'fix/policy-*'
```

**Resolution**:
1. Review logs in fix branch
2. Identify root cause
3. Apply fix
4. Re-run operation
5. Delete fix branch after verified

---

## 9. Emergency Procedures

### Complete System Reset

```bash
# 1. Disable all automation
# - Pause GitHub Actions workflows

# 2. Reset all safety mechanisms (see section 5)

# 3. Reset policy state
rm state/policy_state.json state/policy_state_log.jsonl
python scripts/policy/policy_orchestrator.py --run

# 4. Verify GREEN state
cat state/policy_state.json | jq '.policy'

# 5. Re-enable automation if GREEN
```

### Disable Automated Responses

**In GitHub Actions**:
1. Go to Settings → Secrets and variables → Actions
2. Set `POLICY_AUTO_APPLY` to `false`
3. Or disable "Policy Response Runner" workflow

**Locally**:
```bash
# Always run in dry-run mode (omit --apply flag)
python scripts/response/run_policy_responses.py --policy RED
```

---

## 10. Quick Command Reference

```bash
# Orchestrate policy
python scripts/policy/policy_orchestrator.py --run

# Preview responses
python scripts/response/run_policy_responses.py --policy YELLOW
python scripts/response/run_policy_responses.py --policy RED

# Execute responses
python scripts/response/run_policy_responses.py --policy RED --apply

# Check policy state
cat state/policy_state.json

# Check response preview
cat state/policy_response_preview.json

# Check execution log
cat state/policy_response_log.jsonl | tail -n 1

# Check blocked reports
cat reports/policy_response_blocked.json

# Force unlock trust guard
python scripts/trust/trust_guard_controller.py --force-unlock --reason "manual-override"

# Reset safety brake
# Edit forensics/safety_brake_state.json: is_engaged=false, response_count_24h=0

# List undo files
ls state/policy_response_undo_*.json

# Execute undo (example)
cp mirrors/anchor_chain.json.backup mirrors/anchor_chain.json
```

---

## 11. Operational Metrics

**Safe Operation Indicators**:
- Policy flips < 3 times per 24h
- Safety brake engaged < 2 times per week
- Response blocked count < 5% of total runs
- Manual unlock usage < 50% of daily limit

**Alert Thresholds**:
- Policy RED > 4 hours → Investigate
- Safety brake engaged > 24 hours → Manual intervention required
- Response blocked > 3 consecutive times → Check safety gates
- Fix branch created → Review logs immediately

---

## 12. Contact & Escalation

**Automated Alerts**: GitHub Issues created for high-priority conditions

**Manual Escalation**:
1. Review `audit_summary.md` for markers
2. Check CI workflow artifacts
3. Examine fix branches for detailed logs
4. Consult Phase XXV documentation: `PHASE_XXV_COMPLETION_REPORT.md`

---

**End of Runbook**
