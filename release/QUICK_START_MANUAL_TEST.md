# Quick Start: Manual Workflow Test

Run these commands in PowerShell to test the release utilities workflow:

## Prerequisites

```powershell
# Verify GitHub CLI installed
gh --version

# Authenticate (if needed)
gh auth login
```

## Test Sequence

### 1. Trigger Workflow

```powershell
gh workflow run release_utilities.yml
```

### 2. Monitor Execution

```powershell
# Watch in real-time
gh run watch

# OR check status
gh run list --workflow=release_utilities.yml --limit 3
```

### 3. Verify Capsule Tag

```powershell
# Fetch latest tags from remote
git fetch --tags

# List all capsule tags
git tag --list "capsule-*"
```

**Expected output:**
```
capsule-2025-11-11
```

### 4. Inspect Tag Details

```powershell
git show capsule-2025-11-11
```

**Expected annotation:**
```
tag capsule-2025-11-11
Tagger: release-bot <actions@github.com>
Date:   Mon Nov 11 ... 2025

Governance reproducibility capsule 2025-11-11
```

### 5. Test Idempotency

```powershell
# Run workflow again
gh workflow run release_utilities.yml

# Wait for completion
gh run watch

# Check logs for skip message
gh run view --log | Select-String "already exists"
```

**Expected log message:**
```
Tag capsule-2025-11-11 already exists; skipping creation
```

## Success Criteria

- ✅ Workflow completes without errors
- ✅ Tag `capsule-2025-11-11` exists on remote
- ✅ Tag annotation includes "Governance reproducibility capsule"
- ✅ Second run skips tag creation (idempotent)

## Troubleshooting

**Workflow not found?**
```powershell
# Ensure workflow is committed and pushed
git status .github/workflows/release_utilities.yml
git push origin main
```

**Permission denied?**
```powershell
# Refresh authentication with write scope
gh auth refresh -s write:packages,write:org
```

**Tag not appearing?**
```powershell
# Force fetch all tags
git fetch --tags --force

# Check remote tags
git ls-remote --tags origin
```

## Next Steps

After successful test:

1. ✅ Workflow is ready for production releases
2. ✅ Review `release/ZENODO_RELEASE_CHECKLIST.md` for full release process
3. ✅ Update `zenodo_metadata.json` with accurate information
4. ✅ Generate reproducibility capsule before first release

---

**For full testing guide**: See `release/DRY_RUN_TESTING_GUIDE.md`  
**For Zenodo setup**: See `release/ZENODO_RELEASE_CHECKLIST.md`
