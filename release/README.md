# Release Documentation

This directory contains all documentation and automation tools for publishing Zenodo DOI releases of the Reflex Governance Architecture.

---

## 📋 Quick Start

**First-time release?** Follow this sequence:

1. **[QUICK_START_MANUAL_TEST.md](QUICK_START_MANUAL_TEST.md)** ← Start here
   - Test the release workflow (5 minutes)
   - Verify capsule tagging works correctly

2. **[PRE_RELEASE_VALIDATION.ps1](PRE_RELEASE_VALIDATION.ps1)** ← Run this script
   - Comprehensive validation checklist (10 minutes)
   - Ensures all systems ready for release

3. **[ZENODO_RELEASE_CHECKLIST.md](ZENODO_RELEASE_CHECKLIST.md)** ← Follow this guide
   - Step-by-step Zenodo setup (30 minutes)
   - GitHub release publication
   - DOI propagation verification

---

## 📁 File Index

### Core Guides

| File | Purpose | When to Use |
|------|---------|-------------|
| **QUICK_START_MANUAL_TEST.md** | Quick workflow test commands | Before first release (5 min) |
| **PRE_RELEASE_VALIDATION.ps1** | Automated validation script | Before every release (10 min) |
| **ZENODO_RELEASE_CHECKLIST.md** | Complete release process | During release publication (30 min) |
| **RELEASE_PREPARATION_v1.0.0.md** | Comprehensive pre-release checklist | Planning phase (1 hour) |
| **DRY_RUN_TESTING_GUIDE.md** | Detailed testing procedures | Troubleshooting (as needed) |
| **RELEASE_AUTOMATION_SUMMARY.md** | Architecture overview | Understanding the system (15 min read) |
| **REPRODUCIBILITY_BADGE_GUIDE.md** | Badge generation & verification | Understanding badges (10 min read) |

### Release Notes

| File | Version | Date |
|------|---------|------|
| **BioSignal-X-v1.0.0-release-notes.md** | v1.0.0-Whitepaper | 2025-11-11 (planned) |

---

## 🚀 Release Workflow Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    PREPARATION PHASE                            │
├─────────────────────────────────────────────────────────────────┤
│ 1. Run PRE_RELEASE_VALIDATION.ps1                              │
│    └─ Verifies: scripts, workflows, artifacts, tests           │
│                                                                  │
│ 2. Generate reproducibility capsule                             │
│    └─ python scripts/workflow_utils/export_reproducibility...  │
│                                                                  │
│ 3. Review zenodo_metadata.json                                  │
│    └─ Update ORCID, dates, related identifiers                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    ZENODO SETUP PHASE                           │
├─────────────────────────────────────────────────────────────────┤
│ 1. Link Zenodo to GitHub repository                             │
│    └─ https://zenodo.org/account/settings/github/              │
│                                                                  │
│ 2. Enable webhook for BioSignal-AI                             │
│    └─ Toggle ON in Zenodo dashboard                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    RELEASE PHASE                                │
├─────────────────────────────────────────────────────────────────┤
│ 1. Create GitHub Release                                        │
│    └─ Tag: v1.0.0-Whitepaper, Target: main                     │
│                                                                  │
│ 2. Zenodo mints DOI (automatic, 5-10 minutes)                  │
│    └─ Creates zenodo.json in repository                        │
│                                                                  │
│ 3. release_utilities.yml workflow triggers (automatic)          │
│    └─ Propagates DOI, creates capsule tag                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    VERIFICATION PHASE                           │
├─────────────────────────────────────────────────────────────────┤
│ 1. Verify DOI in README, whitepaper, manifest script           │
│    └─ git pull; Select-String "10.5281/zenodo"                │
│                                                                  │
│ 2. Verify capsule tag created                                  │
│    └─ git fetch --tags; git tag --list "capsule-*"            │
│                                                                  │
│ 3. Add Zenodo badge to README                                  │
│    └─ Copy badge markdown from Zenodo record page             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Key Automation Scripts

Located in `scripts/workflow_utils/`:

| Script | Purpose | Trigger |
|--------|---------|---------|
| `update_doi_reference.py` | Propagates Zenodo DOI to documentation | `release_utilities.yml` |
| `export_reproducibility_capsule.py` | Bundles governance artifacts into ZIP | Manual / scheduled |

---

## 📊 Validation Checklist

Before publishing a release, ensure:

- [x] All governance scripts compiled without errors
- [x] Workflow YAML syntax validated
- [x] `zenodo_metadata.json` has 10+ keywords, methodology block, 4+ related IDs
- [x] Governance artifacts exist (registry CSV, ledger JSONL, badge JSON)
- [x] Reproducibility capsule generated with manifest
- [x] DOI updater test passed (dry run with mock DOI)
- [x] Integrity score ≥90% (green badge)
- [x] Test suite passes (pytest)
- [x] Manual workflow trigger test successful
- [x] Capsule tag created: `capsule-YYYY-MM-DD`

**Run `PRE_RELEASE_VALIDATION.ps1` to automate these checks.**

---

## 🆘 Troubleshooting

### Common Issues

**Issue**: Workflow doesn't trigger after release  
**Solution**: Manually run `gh workflow run release_utilities.yml`

**Issue**: DOI updater finds no `zenodo.json`  
**Solution**: Manually create file with DOI from Zenodo dashboard

**Issue**: Capsule tag already exists  
**Solution**: This is normal (idempotent behavior), no action needed

**Issue**: Integrity score below 90%  
**Solution**: Review violations in `exports/integrity_metrics_registry.csv` before release

**Full troubleshooting**: See [DRY_RUN_TESTING_GUIDE.md](DRY_RUN_TESTING_GUIDE.md) Section 12

---

## 📖 Additional Resources

### External Links

- **Zenodo Documentation**: https://help.zenodo.org/
- **GitHub Releases Guide**: https://docs.github.com/en/repositories/releasing-projects-on-github
- **shields.io Endpoint Badges**: https://shields.io/endpoint

### Repository Files

- **Governance Whitepaper**: `docs/GOVERNANCE_WHITEPAPER.md`
- **Transparency Manifest**: `GOVERNANCE_TRANSPARENCY.md` (auto-generated nightly)
- **Zenodo Metadata Template**: `zenodo_metadata.json`
- **Workflow Definitions**: `.github/workflows/release_utilities.yml`

---

## 🎯 Success Criteria

A successful release includes:

✅ **GitHub Release**: Published with tag `v1.0.0-Whitepaper`  
✅ **Zenodo DOI**: Minted and visible at `https://doi.org/10.5281/zenodo.XXXXXXX`  
✅ **DOI Propagation**: Appears in README, whitepaper, manifest script  
✅ **Capsule Tag**: Created with name `capsule-YYYY-MM-DD`  
✅ **Badge Integration**: Zenodo badge visible on README  
✅ **Transparency Updated**: Nightly manifest includes final DOI  
✅ **Integrity Score**: ≥90% (green badge)  

---

## 📅 Release Cadence

**Planned Schedule**:

- **v1.0.0-Whitepaper**: First citable release with full documentation
- **v1.1.0**: Quarterly update (3 months after v1.0.0)
- **v2.0.0**: Major version when breaking schema changes occur

**Capsule Tags**: Created daily on workflow runs (idempotent per date)

**Weekly Snapshots**: Archived every Sunday at 03:00 UTC in `archives/transparency_snapshots/`

---

## 🤝 Contributing

Found an issue in the release process? Please:

1. Check [DRY_RUN_TESTING_GUIDE.md](DRY_RUN_TESTING_GUIDE.md) troubleshooting section
2. Review [RELEASE_AUTOMATION_SUMMARY.md](RELEASE_AUTOMATION_SUMMARY.md) for architecture details
3. Open an issue in the repository with:
   - Steps to reproduce
   - Expected vs actual behavior
   - Workflow logs (if applicable)

---

## 📜 License

Release documentation and automation scripts are covered by the repository's MIT License.

---

**Last Updated**: 2025-11-11  
**Documentation Version**: 1.0  
**Next Milestone**: v1.0.0-Whitepaper release
