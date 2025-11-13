# Reproducibility Badge & Release Verification

This document explains the automated badge generation and cross-reference verification added to the release workflow.

---

## Overview

The release utilities workflow now includes:

1. **Dual Badge Generation**: Creates both `integrity_status.json` and `reproducibility_status.json` badges
2. **Release Integrity Verification**: Validates DOI and capsule tag cross-references in governance documentation

---

## Reproducibility Badge

### Purpose

The reproducibility badge provides a visual "health stamp" for each release, reflecting the mean integrity score from the governance metrics registry.

### Badge Endpoints

- **Integrity Badge**: `badges/integrity_status.json`
- **Reproducibility Badge**: `badges/reproducibility_status.json`

Both badges are generated from the same data source (`exports/integrity_metrics_registry.csv`) but allow for separate labeling and future differentiation.

### Badge Format (shields.io)

```json
{
  "label": "Reproducibility",
  "message": "97%",
  "color": "green"
}
```

### Color Thresholds

- 🟢 **Green**: Score ≥90 (High Integrity)
- 🟡 **Yellow**: 70 ≤ Score < 90 (Stable)
- 🔴 **Red**: Score < 70 (Review Required)
- ⚪ **Light Grey**: No data available

### README Integration

Both badges appear in the README header:

```markdown
![Integrity](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/dhananjaysmvdu/BioSignal-AI/main/badges/integrity_status.json)
![Reproducibility](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/dhananjaysmvdu/BioSignal-AI/main/badges/reproducibility_status.json)

> **Governance Health:** Live integrity and reproducibility scores updated with each release.  
> Scores ≥90 = 🟢 High Integrity | 70–89 = 🟡 Stable | <70 = 🔴 Review Required
```

### Manual Generation

Generate badges manually with optional custom labels:

```bash
# Default: generates badges/integrity_status.json with label "Integrity"
python scripts/workflow_utils/generate_integrity_status_badge.py

# Custom output path (label auto-detected as "Reproducibility")
python scripts/workflow_utils/generate_integrity_status_badge.py \
  --output badges/reproducibility_status.json

# Custom label and paths
python scripts/workflow_utils/generate_integrity_status_badge.py \
  --input exports/integrity_metrics_registry.csv \
  --output badges/custom_badge.json \
  --label "Custom Health"
```

---

## Release Integrity Verification

### Purpose

Ensures that the latest Zenodo DOI and reproducibility capsule tag are properly cross-referenced in key governance documents after each release.

### Script: `verify_release_integrity.py`

**Location**: `scripts/workflow_utils/verify_release_integrity.py`

### What It Checks

1. **DOI Presence**:
   - Reads DOI from `zenodo.json` or `zenodo_metadata.json`
   - Verifies DOI appears in:
     - `docs/GOVERNANCE_WHITEPAPER.md`
     - `GOVERNANCE_TRANSPARENCY.md`

2. **Capsule Tag Presence**:
   - Retrieves latest `capsule-*` tag from Git
   - Verifies tag or date appears in:
     - `docs/GOVERNANCE_WHITEPAPER.md`
     - `GOVERNANCE_TRANSPARENCY.md`

3. **File Existence**:
   - Confirms governance documentation files exist

### Output Format

```
======================================================================
RELEASE INTEGRITY VERIFICATION
======================================================================

📄 DOI Found: https://doi.org/10.5281/zenodo.123456
   Source: zenodo.json

📦 Latest Capsule Tag: capsule-2025-11-11
   Commit SHA: a3f29c1

----------------------------------------------------------------------
CROSS-REFERENCE VERIFICATION
----------------------------------------------------------------------

✅ DOI in GOVERNANCE_WHITEPAPER.md
✅ DOI in GOVERNANCE_TRANSPARENCY.md

✅ Capsule tag/date in GOVERNANCE_WHITEPAPER.md
✅ Capsule tag/date in GOVERNANCE_TRANSPARENCY.md

----------------------------------------------------------------------
DOCUMENTATION FILE CHECKS
----------------------------------------------------------------------

✅ GOVERNANCE_WHITEPAPER.md exists
✅ GOVERNANCE_TRANSPARENCY.md exists

======================================================================
SUMMARY
======================================================================

Checks Passed: 6/6
✅ All verification checks passed!

======================================================================
Note: This is a soft check. Workflow will continue regardless of results.
======================================================================
```

### Exit Behavior

**Always exits with code 0** (soft check) to avoid blocking CI pipeline. Verification failures are logged but don't halt workflow execution.

### Manual Verification

Run manually at any time:

```bash
python scripts/workflow_utils/verify_release_integrity.py
```

### Expected Behavior Before First Release

```
⚠️  No DOI found in zenodo metadata files
   This is expected before first Zenodo release.

⚠️  No capsule tags found
   Run workflow manually to create first capsule tag.
```

This is **normal** and will not block workflow execution.

---

## Workflow Integration

### Workflow File: `release_utilities.yml`

**Trigger**: 
- `release: published` (automatic)
- `workflow_dispatch` (manual)

### Job Sequence

```
1. Propagate Zenodo DOI
   └─ Run update_doi_reference.py
   
2. Push DOI updates
   └─ Commit if changes detected
   
3. Tag reproducibility capsule
   └─ Create capsule-YYYY-MM-DD tag (idempotent)
   
4. Generate reproducibility badge (NEW)
   └─ Generate integrity_status.json
   └─ Generate reproducibility_status.json
   └─ Commit and push badges
   
5. Verify release integrity (NEW)
   └─ Run verify_release_integrity.py
   └─ Print cross-reference status
```

### Workflow YAML Snippet

```yaml
- name: Generate reproducibility badge
  run: |
    python scripts/workflow_utils/generate_integrity_status_badge.py || true
    python scripts/workflow_utils/generate_integrity_status_badge.py --output badges/reproducibility_status.json || true
    git add badges/integrity_status.json badges/reproducibility_status.json || true
    if git diff --cached --quiet; then
      echo "No badge changes to commit"
    else
      git commit -m "docs: update governance health badges"
      git push
      echo "Governance badges updated"
    fi

- name: Verify release integrity
  run: |
    python scripts/workflow_utils/verify_release_integrity.py || true
```

---

## Testing

### Test Badge Generation

```powershell
# Generate both badges
python scripts/workflow_utils/generate_integrity_status_badge.py
python scripts/workflow_utils/generate_integrity_status_badge.py --output badges/reproducibility_status.json

# Verify badges created
Test-Path badges/integrity_status.json
Test-Path badges/reproducibility_status.json

# Inspect badge content
Get-Content badges/integrity_status.json | ConvertFrom-Json
Get-Content badges/reproducibility_status.json | ConvertFrom-Json
```

**Expected Output**:
```json
{"label": "Integrity", "message": "n/a", "color": "lightgrey"}
{"label": "Reproducibility", "message": "n/a", "color": "lightgrey"}
```

(Shows "n/a" until integrity metrics registry is populated)

### Test Release Verification

```powershell
# Test with mock DOI
python -c "import json; json.dump({'doi': '10.5281/zenodo.123456'}, open('zenodo.json', 'w'))"
python scripts/workflow_utils/verify_release_integrity.py
Remove-Item zenodo.json
```

**Expected**: Script detects DOI but shows ❌ for cross-references (since mock DOI not in docs)

### Test Full Workflow

```powershell
# Trigger release utilities workflow manually
gh workflow run release_utilities.yml

# Wait for completion
gh run watch

# Verify outputs
git fetch --tags
git tag --list "capsule-*"
git pull origin main
Test-Path badges/reproducibility_status.json
```

---

## Troubleshooting

### Issue: Badge shows "n/a"

**Cause**: `exports/integrity_metrics_registry.csv` is empty or missing  
**Solution**: Run weekly audit workflow to populate registry:
```powershell
gh workflow run audit_provenance_history.yml
```

### Issue: Verification script shows all ❌

**Cause**: DOI or capsule tag not yet in documentation  
**Expected**: This is normal before first release  
**Action**: DOI updater will automatically populate after Zenodo minting

### Issue: Badge color not updating

**Cause**: shields.io CDN cache (5-10 minutes)  
**Solution**: Wait or force refresh with cache-busting query:
```
?cache=bust-timestamp
```

### Issue: Verification script fails to parse JSON

**Cause**: UTF-8 BOM from PowerShell Out-File  
**Solution**: Script now handles both UTF-8 and UTF-8-SIG encodings automatically

---

## Future Enhancements

### Potential Additions

1. **Separate Reproducibility Metrics**:
   - Track capsule generation success rate
   - Monitor reproducibility test pass/fail ratio
   - Separate badge data source from integrity metrics

2. **Historical Badge Trends**:
   - Generate sparkline showing score trends over time
   - Embed in badge message: "97% ▲"

3. **Multi-Badge Dashboard**:
   - Create `badges/dashboard.json` with all health indicators
   - Single endpoint for comprehensive status

4. **Automated Badge Updates**:
   - Trigger badge regeneration on nightly transparency workflow
   - Keep badges fresh even without releases

---

## References

- **Badge Generator**: `scripts/workflow_utils/generate_integrity_status_badge.py`
- **Verification Script**: `scripts/workflow_utils/verify_release_integrity.py`
- **Workflow**: `.github/workflows/release_utilities.yml`
- **shields.io Docs**: https://shields.io/endpoint

---

**Last Updated**: 2025-11-11  
**Version**: 1.0  
**Status**: Production Ready ✅
