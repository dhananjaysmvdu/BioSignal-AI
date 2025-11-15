Draft PR: Fix Forensics Test Failures (Phase XX E2E)

Summary:
- Failing tests persist after single retry:
  - tests/forensics/test_mirror_integrity_anchor.py::test_anchor_chain_continuity
  - tests/forensics/test_snapshot_ledger_state.py::test_snapshot_creation_hash_and_prune
  - tests/forensics/test_verify_cold_storage.py::test_cold_storage_verification_logs_and_markers
- Logs attached under logs/phase_xx_run_2025-11-14/

Reproduction steps:
1. Run `pytest -q tests/forensics/test_mirror_integrity_anchor.py::test_anchor_chain_continuity`
2. Run `pytest -q tests/forensics/test_snapshot_ledger_state.py::test_snapshot_creation_hash_and_prune`
3. Run `pytest -q tests/forensics/test_verify_cold_storage.py::test_cold_storage_verification_logs_and_markers`

Observed:
- Mirror chain file not created
- Snapshot tarballs not found/pruned
- Cold storage verification log not written

Next Actions:
- Inspect scripts in scripts/forensics/: mirror_integrity_anchor.py, snapshot_ledger_state.py, verify_cold_storage.py for ROOT path handling and file writes in temp dirs
- Ensure per-test monkeypatching of ROOT results in expected output directories being created and used
