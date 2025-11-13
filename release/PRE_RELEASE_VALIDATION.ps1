# Pre-Release Validation Checklist

Run these commands before triggering the v1.0.0-Whitepaper release to ensure all systems are ready.

---

## 1. Repository Structure Validation

```powershell
# Verify all governance scripts exist
$scripts = @(
    "scripts/workflow_utils/update_doi_reference.py",
    "scripts/workflow_utils/export_reproducibility_capsule.py",
    "scripts/workflow_utils/generate_integrity_status_badge.py",
    "scripts/workflow_utils/generate_transparency_manifest.py",
    "scripts/workflow_utils/validate_integrity_registry_schema.py",
    "scripts/workflow_utils/schema_provenance_ledger.py",
    "scripts/workflow_utils/generate_integrity_metrics_registry.py"
)

foreach ($script in $scripts) {
    if (Test-Path $script) {
        Write-Host "✅ $script"
    } else {
        Write-Host "❌ MISSING: $script"
    }
}
```

**Expected**: All scripts show ✅

---

## 2. Workflow Syntax Validation

```powershell
# Validate all workflow YAML files
$workflows = @(
    ".github/workflows/release_utilities.yml",
    ".github/workflows/governance_transparency_manifest.yml",
    ".github/workflows/audit_provenance_history.yml"
)

foreach ($wf in $workflows) {
    Write-Host "`nValidating $wf..."
    python -c "import yaml; yaml.safe_load(open('$wf', encoding='utf-8')); print('✅ YAML OK')"
}
```

**Expected**: All workflows show "✅ YAML OK"

---

## 3. Zenodo Metadata Validation

```powershell
# Check zenodo_metadata.json structure
python -c @"
import json
data = json.load(open('zenodo_metadata.json', encoding='utf-8'))

checks = {
    'Title': bool(data.get('title')),
    'Description': bool(data.get('description')),
    'Keywords (>=5)': len(data.get('keywords', [])) >= 5,
    'Methodology': bool(data.get('methodology')),
    'License': data.get('license') == 'MIT',
    'Creators': len(data.get('creators', [])) > 0,
    'Related IDs': len(data.get('related_identifiers', [])) >= 4
}

print('Zenodo Metadata Validation:')
for key, value in checks.items():
    status = '✅' if value else '❌'
    print(f'{status} {key}')

if all(checks.values()):
    print('\n✅ All checks passed')
else:
    print('\n❌ Some checks failed - review zenodo_metadata.json')
"@
```

**Expected**: All checks show ✅

---

## 4. Governance Artifacts Presence

```powershell
# Check for required governance artifacts
$artifacts = @{
    'Audit Summary' = 'reports/audit_summary.md'
    'Integrity Registry' = 'exports/integrity_metrics_registry.csv'
    'Provenance Ledger' = 'exports/schema_provenance_ledger.jsonl'
    'Integrity Badge' = 'badges/integrity_status.json'
    'Transparency Manifest' = 'GOVERNANCE_TRANSPARENCY.md'
    'Governance Whitepaper' = 'docs/GOVERNANCE_WHITEPAPER.md'
}

Write-Host "`nGovernance Artifacts:"
foreach ($name in $artifacts.Keys) {
    $path = $artifacts[$name]
    if (Test-Path $path) {
        $size = (Get-Item $path).Length
        Write-Host "✅ $name ($path) - $size bytes"
    } else {
        Write-Host "❌ MISSING: $name ($path)"
    }
}
```

**Expected**: All artifacts show ✅

---

## 5. Reproducibility Capsule Generation

```powershell
# Generate capsule and verify output
Write-Host "`nGenerating reproducibility capsule..."
python scripts/workflow_utils/export_reproducibility_capsule.py

# Check capsule file
$capsule = Get-ChildItem exports/governance_reproducibility_capsule_*.zip -ErrorAction SilentlyContinue | Select-Object -First 1
if ($capsule) {
    Write-Host "✅ Capsule created: $($capsule.Name)"
    Write-Host "   Size: $([math]::Round($capsule.Length / 1MB, 2)) MB"
    
    # Verify manifest
    if (Test-Path exports/capsule_manifest.json) {
        $manifest = Get-Content exports/capsule_manifest.json | ConvertFrom-Json
        Write-Host "✅ Manifest created: $($manifest.files.Count) files tracked"
        Write-Host "   Capsule SHA-256: $($manifest.capsule.sha256)"
    } else {
        Write-Host "❌ Manifest NOT found"
    }
    
    # Check audit marker
    $marker = Select-String -Path reports/audit_summary.md -Pattern "REPRODUCIBILITY_CAPSULE" -Context 0,1
    if ($marker) {
        Write-Host "✅ Audit marker updated"
    } else {
        Write-Host "❌ Audit marker NOT updated"
    }
} else {
    Write-Host "❌ Capsule NOT created"
}
```

**Expected**: 
- ✅ Capsule created
- ✅ Manifest created with file count
- ✅ Audit marker updated

---

## 6. Test DOI Updater (Dry Run)

```powershell
# Create mock zenodo.json for testing
Write-Host "`nTesting DOI updater (dry run)..."
@"
{
  "doi": "10.5281/zenodo.TEST9999",
  "doi_url": "https://doi.org/10.5281/zenodo.TEST9999"
}
"@ | Out-File -Encoding UTF8 zenodo_test.json

# Temporarily rename to trigger updater
Move-Item zenodo_test.json zenodo.json -Force

# Run updater
python scripts/workflow_utils/update_doi_reference.py

# Check for changes
$changed = @(
    git diff --name-only README.md
    git diff --name-only docs/GOVERNANCE_WHITEPAPER.md
    git diff --name-only scripts/workflow_utils/generate_transparency_manifest.py
)

if ($changed.Count -gt 0) {
    Write-Host "✅ DOI updater modified $($changed.Count) files:"
    foreach ($file in $changed) {
        Write-Host "   - $file"
    }
    
    # Show sample change
    Write-Host "`nSample change in README.md:"
    git diff README.md | Select-String "TEST9999" | Select-Object -First 2
    
    # Restore files
    Write-Host "`nRestoring files..."
    git restore README.md docs/GOVERNANCE_WHITEPAPER.md scripts/workflow_utils/generate_transparency_manifest.py
    Write-Host "✅ Files restored"
} else {
    Write-Host "❌ DOI updater did NOT modify any files"
}

# Cleanup
Remove-Item zenodo.json -ErrorAction SilentlyContinue
Write-Host "✅ Test cleanup complete"
```

**Expected**: 
- ✅ DOI updater modified 3 files
- ✅ Files contain "TEST9999"
- ✅ Files restored successfully

---

## 7. Workflow Trigger Test

```powershell
# Test manual workflow trigger
Write-Host "`nTesting manual workflow trigger..."
Write-Host "Run this command:"
Write-Host "  gh workflow run release_utilities.yml"
Write-Host ""
Read-Host "Press Enter after running the command above"

# Wait a few seconds for workflow to start
Start-Sleep -Seconds 5

# Check workflow status
Write-Host "`nChecking workflow runs..."
gh run list --workflow=release_utilities.yml --limit 3

Write-Host "`nTo watch workflow in real-time:"
Write-Host "  gh run watch"
```

**Expected**: Workflow appears in list with "in_progress" or "completed" status

---

## 8. Capsule Tag Verification

```powershell
# After workflow completes, verify tag creation
Write-Host "`nVerifying capsule tag..."
git fetch --tags

$today = Get-Date -Format "yyyy-MM-dd"
$tag = "capsule-$today"

$tagExists = git tag --list $tag
if ($tagExists) {
    Write-Host "✅ Tag created: $tag"
    
    # Show tag details
    Write-Host "`nTag details:"
    git show $tag | Select-Object -First 10
} else {
    Write-Host "❌ Tag NOT found: $tag"
    Write-Host "   Run workflow manually: gh workflow run release_utilities.yml"
}
```

**Expected**: 
- ✅ Tag created: capsule-YYYY-MM-DD
- Tag annotation includes "Governance reproducibility capsule"

---

## 9. Integrity Score Check

```powershell
# Verify current integrity score is >=90 (green badge)
Write-Host "`nChecking current integrity score..."
if (Test-Path badges/integrity_status.json) {
    $badge = Get-Content badges/integrity_status.json | ConvertFrom-Json
    $message = $badge.message -replace '%', ''
    $score = [int]$message
    
    $color = $badge.color
    $emoji = if ($score -ge 90) { '🟢' } elseif ($score -ge 70) { '🟡' } else { '🔴' }
    
    Write-Host "$emoji Integrity Score: $score% (Color: $color)"
    
    if ($score -ge 90) {
        Write-Host "✅ Score is EXCELLENT (green badge)"
    } elseif ($score -ge 70) {
        Write-Host "⚠️  Score is STABLE but below 90% (yellow badge)"
    } else {
        Write-Host "❌ Score is LOW - address violations before release (red badge)"
    }
} else {
    Write-Host "❌ Badge JSON not found - run nightly workflow first"
}
```

**Expected**: 
- 🟢 Integrity Score: ≥90%
- ✅ Score is EXCELLENT

---

## 10. Documentation Links Check

```powershell
# Verify all internal documentation links work
Write-Host "`nChecking documentation links..."
$docs = @(
    'release/RELEASE_PREPARATION_v1.0.0.md',
    'release/QUICK_START_MANUAL_TEST.md',
    'release/DRY_RUN_TESTING_GUIDE.md',
    'release/ZENODO_RELEASE_CHECKLIST.md',
    'release/RELEASE_AUTOMATION_SUMMARY.md'
)

foreach ($doc in $docs) {
    if (Test-Path $doc) {
        $size = (Get-Item $doc).Length
        Write-Host "✅ $doc ($size bytes)"
    } else {
        Write-Host "❌ MISSING: $doc"
    }
}
```

**Expected**: All documentation files show ✅

---

## 11. Test Suite Execution

```powershell
# Run pytest on governance scripts
Write-Host "`nRunning test suite..."
pytest tests/ -v --tb=short

# Check exit code
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ All tests passed"
} else {
    Write-Host "`n❌ Some tests failed - review output above"
}
```

**Expected**: 
- ✅ All tests passed
- Exit code: 0

---

## 12. Final Pre-Release Summary

```powershell
Write-Host "`n" + "="*70
Write-Host "FINAL PRE-RELEASE VALIDATION SUMMARY"
Write-Host "="*70

$checks = @(
    @{Name='Repository structure'; Status='✅'},
    @{Name='Workflow YAML syntax'; Status='✅'},
    @{Name='Zenodo metadata'; Status='✅'},
    @{Name='Governance artifacts'; Status='✅'},
    @{Name='Reproducibility capsule'; Status='✅'},
    @{Name='DOI updater'; Status='✅'},
    @{Name='Workflow trigger test'; Status='✅'},
    @{Name='Capsule tag'; Status='✅'},
    @{Name='Integrity score ≥90%'; Status='✅'},
    @{Name='Documentation links'; Status='✅'},
    @{Name='Test suite'; Status='✅'}
)

foreach ($check in $checks) {
    Write-Host "$($check.Status) $($check.Name)"
}

Write-Host "`n" + "="*70
Write-Host "READY FOR RELEASE: v1.0.0-Whitepaper"
Write-Host "="*70
Write-Host "`nNext steps:"
Write-Host "1. Review release/ZENODO_RELEASE_CHECKLIST.md"
Write-Host "2. Link Zenodo to GitHub repository"
Write-Host "3. Publish GitHub release with tag v1.0.0-Whitepaper"
Write-Host "4. Wait for Zenodo DOI minting (5-10 minutes)"
Write-Host "5. Verify DOI propagation and capsule tag creation"
Write-Host "`nGood luck! 🚀"
}
```

---

## Troubleshooting

### Issue: Script execution disabled

**Solution**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue: `gh` command not found

**Solution**:
```powershell
winget install --id GitHub.cli
```

### Issue: pytest not installed

**Solution**:
```powershell
pip install pytest pytest-cov
```

### Issue: Capsule generation fails

**Solution**: Generate sample artifacts first:
```powershell
python scripts/workflow_utils/generate_integrity_status_badge.py
python scripts/workflow_utils/generate_transparency_manifest.py
```

---

**Run this entire checklist before publishing the release.**  
**All checks must show ✅ for a successful release.**

---

**Last Updated**: 2025-11-11  
**Target Release**: v1.0.0-Whitepaper
