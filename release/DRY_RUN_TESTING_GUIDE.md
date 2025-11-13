# Dry-Run Testing Guide: Release Utilities Workflow

This document provides step-by-step instructions for testing the `release_utilities.yml` workflow before the first official release.

---

## Prerequisites

1. **GitHub CLI installed**: Verify with `gh --version` (requires v2.0.0+)
2. **Authenticated**: Run `gh auth status` to confirm you're logged in
3. **Repository access**: Ensure you have push permissions to `dhananjaysmvdu/BioSignal-AI`

---

## Test 1: Manual Workflow Trigger (Capsule Tagging)

### Purpose
Verify that the reproducibility capsule tagging step creates dated tags correctly and idempotently.

### Steps

1. **Trigger the workflow manually**:
   ```powershell
   gh workflow run release_utilities.yml
   ```

2. **Wait for completion** (typically 1-2 minutes):
   ```powershell
   gh run list --workflow=release_utilities.yml --limit 5
   ```

3. **Verify capsule tag was created**:
   ```powershell
   git fetch --tags
   git tag --list "capsule-*"
   ```

   **Expected output**:
   ```
   capsule-2025-11-11
   ```

4. **Inspect tag details**:
   ```powershell
   git show capsule-2025-11-11
   ```

   **Expected output**:
   ```
   tag capsule-2025-11-11
   Tagger: release-bot <actions@github.com>
   Date:   Mon Nov 11 ... 2025

   Governance reproducibility capsule 2025-11-11

   commit <sha>
   ...
   ```

5. **Test idempotency** (run workflow again):
   ```powershell
   gh workflow run release_utilities.yml
   ```

   Check logs to confirm it skips tag creation:
   ```powershell
   gh run view --log
   ```

   **Expected log message**:
   ```
   Tag capsule-2025-11-11 already exists; skipping creation
   ```

### Success Criteria

- ✅ Tag `capsule-2025-11-11` exists on remote
- ✅ Tag annotation includes "Governance reproducibility capsule 2025-11-11"
- ✅ Second run skips tag creation (idempotent)
- ✅ No errors in workflow logs

---

## Test 2: DOI Updater (Requires `zenodo.json`)

### Purpose
Verify the DOI propagation script updates all documentation files correctly.

### Steps

1. **Create a mock Zenodo response file**:
   ```powershell
   @"
   {
     "doi": "10.5281/zenodo.1234567",
     "title": "Autonomous Reflex Governance v1.0.0"
   }
   "@ | Out-File -Encoding UTF8 zenodo.json
   ```

2. **Run the DOI updater locally**:
   ```powershell
   python scripts/workflow_utils/update_doi_reference.py
   ```

3. **Verify updates in target files**:
   ```powershell
   # Check README.md
   Select-String -Path README.md -Pattern "10.5281/zenodo.1234567"

   # Check whitepaper
   Select-String -Path docs/GOVERNANCE_WHITEPAPER.md -Pattern "10.5281/zenodo.1234567"

   # Check manifest generator
   Select-String -Path scripts/workflow_utils/generate_transparency_manifest.py -Pattern "10.5281/zenodo.1234567"
   ```

4. **Check for uncommitted changes**:
   ```powershell
   git status
   ```

   **Expected output**:
   ```
   On branch main
   Changes not staged for commit:
     modified:   README.md
     modified:   docs/GOVERNANCE_WHITEPAPER.md
     modified:   scripts/workflow_utils/generate_transparency_manifest.py
   ```

5. **Review the diff**:
   ```powershell
   git diff README.md
   git diff docs/GOVERNANCE_WHITEPAPER.md
   git diff scripts/workflow_utils/generate_transparency_manifest.py
   ```

6. **Clean up test files**:
   ```powershell
   git restore README.md docs/GOVERNANCE_WHITEPAPER.md scripts/workflow_utils/generate_transparency_manifest.py
   Remove-Item zenodo.json
   ```

### Success Criteria

- ✅ Script exits with code 0
- ✅ All three target files contain the DOI `10.5281/zenodo.1234567`
- ✅ Placeholders `(to be assigned via Zenodo)` are replaced
- ✅ No syntax errors introduced in Python/Markdown files

---

## Test 3: Reproducibility Capsule Export

### Purpose
Verify the capsule exporter creates a valid ZIP archive with manifest and audit marker.

### Steps

1. **Run the capsule exporter**:
   ```powershell
   python scripts/workflow_utils/export_reproducibility_capsule.py
   ```

2. **Verify capsule ZIP was created**:
   ```powershell
   $capsuleFile = Get-ChildItem exports/governance_reproducibility_capsule_*.zip | Select-Object -First 1
   if ($capsuleFile) {
     Write-Host "Capsule created: $($capsuleFile.Name)"
     Write-Host "Size: $([math]::Round($capsuleFile.Length / 1MB, 2)) MB"
   }
   ```

3. **Verify manifest JSON**:
   ```powershell
   Get-Content exports/capsule_manifest.json | ConvertFrom-Json | Format-List
   ```

   **Expected fields**:
   - `generated_on`: `2025-11-11`
   - `capsule.sha256`: 64-character hex string
   - `capsule.file_count`: Integer > 0
   - `files`: Array of objects with `path`, `size`, `sha256`

4. **Verify audit marker update**:
   ```powershell
   Select-String -Path reports/audit_summary.md -Pattern "REPRODUCIBILITY_CAPSULE" -Context 0,2
   ```

   **Expected output**:
   ```
   <!-- REPRODUCIBILITY_CAPSULE:BEGIN -->
   Capsule generated 2025-11-11 (X files, SHA256 verified)
   <!-- REPRODUCIBILITY_CAPSULE:END -->
   ```

5. **Test idempotency** (run again):
   ```powershell
   python scripts/workflow_utils/export_reproducibility_capsule.py
   ```

   **Expected console output**:
   ```
   Reproducibility capsule is already up to date for today.
   ```

6. **Inspect ZIP contents**:
   ```powershell
   Expand-Archive -Path $capsuleFile.FullName -DestinationPath temp_capsule -Force
   Get-ChildItem temp_capsule -Recurse | Select-Object FullName
   Remove-Item temp_capsule -Recurse -Force
   ```

### Success Criteria

- ✅ Capsule ZIP exists in `exports/` with today's date
- ✅ Manifest JSON contains valid SHA-256 hashes
- ✅ Audit marker updated in `reports/audit_summary.md`
- ✅ Second run is idempotent (no duplicate capsule)
- ✅ ZIP contains expected directories: `reports/`, `exports/`, `badges/`, `archives/`

---

## Test 4: Full Release Simulation

### Purpose
Simulate the complete release workflow end-to-end without publishing.

### Steps

1. **Create a draft release locally** (don't publish):
   ```powershell
   gh release create v1.0.0-Whitepaper-TEST `
     --draft `
     --title "Test: Reflex Governance Architecture v1.0.0" `
     --notes "This is a test release draft. Do not publish."
   ```

2. **Trigger the release workflow manually**:
   ```powershell
   gh workflow run release_utilities.yml
   ```

3. **Monitor workflow execution**:
   ```powershell
   gh run watch
   ```

4. **After completion, verify outputs**:
   ```powershell
   # Check for new tags
   git fetch --tags
   git tag --list "capsule-*"

   # Check for DOI update commits (if zenodo.json exists)
   git log --oneline -n 5
   ```

5. **Delete test release draft**:
   ```powershell
   gh release delete v1.0.0-Whitepaper-TEST --yes
   ```

### Success Criteria

- ✅ Workflow completes without errors
- ✅ Capsule tag created (or skipped if already exists)
- ✅ DOI updates committed (if `zenodo.json` present)
- ✅ No unintended side effects on `main` branch

---

## Troubleshooting

### Issue: `gh` command not found

**Solution**: Install GitHub CLI:
```powershell
winget install --id GitHub.cli
```

### Issue: Workflow not found

**Solution**: Ensure the workflow file is committed and pushed:
```powershell
git status .github/workflows/release_utilities.yml
git push origin main
```

### Issue: Permission denied when pushing tags

**Solution**: Check repository permissions:
```powershell
gh auth refresh -s write:packages,write:org
```

### Issue: Capsule exporter fails with "No source files"

**Solution**: Ensure governance artifacts exist:
```powershell
# Generate sample artifacts
python scripts/workflow_utils/generate_integrity_status_badge.py
python scripts/workflow_utils/generate_transparency_manifest.py
```

### Issue: DOI updater doesn't find `zenodo.json`

**Expected**: The script will print "No DOI value found in zenodo metadata; nothing to update." This is normal before the first Zenodo release.

---

## Post-Test Cleanup

After completing all tests:

1. **Remove test capsule** (optional):
   ```powershell
   Remove-Item exports/governance_reproducibility_capsule_*.zip
   Remove-Item exports/capsule_manifest.json
   ```

2. **Reset audit marker** (optional):
   ```powershell
   git restore reports/audit_summary.md
   ```

3. **Keep the capsule tag** (recommended for lineage tracking):
   ```
   # No action needed - tag documents the test run
   ```

---

## Ready for Production Release

Once all tests pass, you're ready to:

1. ✅ Create the real `v1.0.0-Whitepaper` release on GitHub
2. ✅ Wait for Zenodo to mint the DOI (usually <5 minutes)
3. ✅ The `release_utilities.yml` workflow will automatically:
   - Propagate the DOI across documentation
   - Create the `capsule-YYYY-MM-DD` tag
   - Commit changes to `main`

---

**Last Updated**: 2025-11-11  
**Next Review**: After first production release
