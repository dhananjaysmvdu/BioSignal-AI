# Production Deployment Quick Reference

## 🚀 Immediate Launch (5 minutes)

```powershell
# Run automated production launch
.\launch-production.ps1
```

This script:
- Creates all required directories
- Generates both badges with timestamps
- Creates transparency manifest
- Exports reproducibility capsule
- Tracks policy evolution
- Runs validator
- Shows git status summary

**Expected outcome:** All artifacts generated, validator shows what needs attention.

---

## 📋 Manual Checklist (if script fails)

### Step 1: Pre-flight (2 min)
```powershell
# Create directories
New-Item -ItemType Directory -Force -Path exports,reports/history,badges,archives/transparency_snapshots

# Verify Python environment
python --version  # Should be 3.11+
```

### Step 2: Generate Artifacts (3 min)
```powershell
# Badges
python scripts/workflow_utils/generate_integrity_status_badge.py
python scripts/workflow_utils/generate_integrity_status_badge.py --output badges/reproducibility_status.json

# Manifest
python scripts/workflow_utils/generate_transparency_manifest.py

# Capsule
python scripts/workflow_utils/export_reproducibility_capsule.py

# Policy evolution
python scripts/workflow_utils/policy_provenance_diff.py
```

### Step 3: Validate (1 min)
```powershell
python scripts/workflow_utils/validate_full_reproducibility.py
```

### Step 4: Commit Baseline (1 min)
```powershell
git add badges/ exports/ GOVERNANCE_TRANSPARENCY.md
git commit -m "chore: establish governance baseline for v1.0.0"
git push
```

---

## 🎓 GitHub Release (15 minutes)

1. **Go to:** https://github.com/dhananjaysmvdu/BioSignal-AI/releases/new

2. **Fill in:**
   - **Tag:** `v1.0.0-Whitepaper`
   - **Title:** `Reflex Governance Architecture v1.0.0`
   - **Description:** Copy from `release/BioSignal-X-v1.0.0-release-notes.md`

3. **Upload:** `exports/governance_reproducibility_capsule_*.zip`

4. **Publish!**

---

## 🔗 Zenodo Setup (30 minutes)

See `PRODUCTION_DEPLOYMENT.md` for full guide.

**Quick version:**
1. Enable GitHub-Zenodo integration: https://zenodo.org/account/settings/github/
2. Zenodo auto-creates deposit from your release
3. Edit deposit, add metadata from `zenodo_metadata.json`
4. Publish to mint DOI
5. Create `zenodo.json` with DOI
6. Run `python scripts/workflow_utils/update_doi_reference.py`

---

## 📊 Monitoring (Ongoing)

```powershell
# Quick health check (run weekly)
python scripts/workflow_utils/validate_full_reproducibility.py

# Should show:
# ✅ Capsule tag
# ✅ DOI
# ✅ Badges
# ✅ Timestamps
# ✅ Manifest
# ✅ Schema
# RESULT: FULLY REPRODUCIBLE ✔
```

---

## 🆘 Troubleshooting

### Validator shows "missing" for everything
**Fix:** Run `launch-production.ps1` to generate all artifacts.

### Badges show "n/a"
**Normal!** Until you have integrity metrics in `exports/integrity_metrics_registry.csv`, badges will show "n/a". This is expected for first release.

### Capsule tag missing
**Normal pre-release!** Capsule tags are created by the release workflow after you publish. Until then, validator will exit 1.

### Policy tracker finds no changes
**Normal for first run!** If `configs/governance_policy.json` hasn't been committed yet or has no history, tracker will report 0 snapshots.

---

## 📚 Full Documentation

- **Comprehensive guide:** `PRODUCTION_DEPLOYMENT.md`
- **Research roadmap:** `RESEARCH_EXTENSIONS.md`
- **Release checklist:** `release/ZENODO_RELEASE_CHECKLIST.md`
- **Whitepaper:** `docs/GOVERNANCE_WHITEPAPER.md`

---

**Next:** Run `.\launch-production.ps1` and follow the output!
