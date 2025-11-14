# Multi-Layer Trust Guard (Triple-Threshold Locking)

This component enforces a reversible lock on destructive governance actions when any of three trust signals fall below policy thresholds.

- Thresholds (defaults): integrity ≥ 90, weighted_consensus ≥ 92, reputation_index ≥ 85
- Lock window: 60 minutes, Auto-unlock after: 1440 minutes (24h)
- Manual unlocks per day: max 2, tracked in `state/trust_lock_state.json`

Key artifacts:
- Policy: `policy/trust_guard_policy.json`
- Controller: `scripts/trust/trust_guard_controller.py`
- API: `api/trust_guard_api.py`
- State: `state/trust_lock_state.json`
- Log: `state/trust_lock_log.jsonl`

Manual unlock counter reset: The controller resets `manual_unlocks_today` when the date changes (UTC) via `manual_unlocks_last_reset`.

Audit markers (idempotent):
- `<!-- TRUST_GUARD: VERIFIED <UTC> -->`
- `<!-- TRUST_GUARD: LOCKED <UTC> reason: <reason> -->`
- `<!-- TRUST_GUARD: UNLOCKED <UTC> -->`
- `<!-- TRUST_GUARD: MANUAL_UNLOCK <UTC> by <actor> -->`
- `<!-- TRUST_GUARD: TESTS_FAIL <UTC> -->`
- `<!-- TRUST_GUARD: FIX_BRANCH_CREATED <UTC> branch: fix/trust-guard-<timestamp> -->`

Safety:
- All writes are atomic (`*.tmp` then replace)
- Retries: 1s, 3s, 9s backoff
- On persistent errors: fix branch auto-created, diagnostics logged

Usage:
- Check: `python scripts/trust/trust_guard_controller.py --check`
- Enforce: `python scripts/trust/trust_guard_controller.py --enforce`
- Manual: `python scripts/trust/trust_guard_controller.py --force-unlock --reason "Maintenance"`