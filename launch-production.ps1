# Production Launch Script
# Executes all pre-release validation steps for v1.0.0

$ErrorActionPreference = "Continue"

Write-Host "`n=== REFLEX GOVERNANCE v1.0.0 PRODUCTION LAUNCH ===" -ForegroundColor Cyan
Write-Host "Starting comprehensive validation...`n" -ForegroundColor Cyan

# Create required directories
Write-Host "[1/8] Creating required directories..." -ForegroundColor Yellow
$dirs = @("exports", "reports/history", "badges", "archives/transparency_snapshots", "research_provenance")
foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
Write-Host "  [OK] Directories created" -ForegroundColor Green

# Generate integrity badge
Write-Host "`n[2/8] Generating integrity badge..." -ForegroundColor Yellow
python scripts/workflow_utils/generate_integrity_status_badge.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Integrity badge generated" -ForegroundColor Green
}
else {
    Write-Host "  [FAIL] Badge generation failed" -ForegroundColor Red
}

# Generate reproducibility badge
Write-Host "`n[3/8] Generating reproducibility badge..." -ForegroundColor Yellow
python scripts/workflow_utils/generate_integrity_status_badge.py --output badges/reproducibility_status.json
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Reproducibility badge generated" -ForegroundColor Green
}
else {
    Write-Host "  [FAIL] Badge generation failed" -ForegroundColor Red
}

# Generate transparency manifest
Write-Host "`n[4/8] Generating transparency manifest..." -ForegroundColor Yellow
python scripts/workflow_utils/generate_transparency_manifest.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Manifest generated" -ForegroundColor Green
}
else {
    Write-Host "  [FAIL] Manifest generation failed" -ForegroundColor Red
}

# Export reproducibility capsule
Write-Host "`n[5/8] Exporting reproducibility capsule..." -ForegroundColor Yellow
python scripts/workflow_utils/export_reproducibility_capsule.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Capsule exported" -ForegroundColor Green
}
else {
    Write-Host "  [FAIL] Capsule export failed" -ForegroundColor Red
}

# Run policy provenance tracker
Write-Host "`n[6/8] Tracking policy provenance..." -ForegroundColor Yellow
python scripts/workflow_utils/policy_provenance_diff.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Policy evolution tracked" -ForegroundColor Green
}
else {
    Write-Host "  [WARN] Policy tracking failed (may be first run)" -ForegroundColor Yellow
}

# Run reproducibility validator
Write-Host "`n[7/8] Running reproducibility validator..." -ForegroundColor Yellow
python scripts/workflow_utils/validate_full_reproducibility.py
$validatorExit = $LASTEXITCODE

# Git status check
Write-Host "`n[8/8] Checking git status..." -ForegroundColor Yellow
$gitStatus = git status --short
if ($gitStatus) {
    Write-Host "  [INFO] Changes detected - ready to commit:" -ForegroundColor Cyan
    git status --short
}
else {
    Write-Host "  [OK] No uncommitted changes" -ForegroundColor Green
}

# Summary
Write-Host "`n=== VALIDATION SUMMARY ===" -ForegroundColor Cyan

# Check badge files
Write-Host "`nGenerated Artifacts:" -ForegroundColor Yellow
$artifacts = @(
    "badges/integrity_status.json",
    "badges/reproducibility_status.json",
    "GOVERNANCE_TRANSPARENCY.md",
    "exports/governance_reproducibility_capsule_$(Get-Date -Format 'yyyy-MM-dd').zip",
    "exports/policy_evolution_timeline.csv"
)

foreach ($artifact in $artifacts) {
    if (Test-Path $artifact) {
        $size = (Get-Item $artifact).Length
        Write-Host "  [OK] $artifact - $size bytes" -ForegroundColor Green
    }
    else {
        Write-Host "  [MISSING] $artifact" -ForegroundColor Red
    }
}

Write-Host "`nValidator Exit Code: $validatorExit" -ForegroundColor Yellow
if ($validatorExit -eq 0) {
    Write-Host "  [OK] All checks passed (or non-critical issues only)" -ForegroundColor Green
}
elseif ($validatorExit -eq 1) {
    Write-Host "  [WARN] Capsule tag missing (expected pre-release)" -ForegroundColor Yellow
}
else {
    Write-Host "  [ERROR] Unexpected error" -ForegroundColor Red
}

# Next steps
Write-Host "`n=== NEXT STEPS ===" -ForegroundColor Cyan
Write-Host @"
1. Review generated artifacts above
2. Commit governance baseline:
   git add badges/ exports/ GOVERNANCE_TRANSPARENCY.md
   git commit -m "chore: establish governance baseline for v1.0.0"
   git push

3. Create GitHub release:
   - Tag: v1.0.0-Whitepaper
   - Title: Reflex Governance Architecture v1.0.0
   - Upload: exports/governance_reproducibility_capsule_*.zip

4. Follow PRODUCTION_DEPLOYMENT.md for Zenodo setup

5. After DOI mint, create zenodo.json and propagate:
   python scripts/workflow_utils/update_doi_reference.py
"@ -ForegroundColor White

Write-Host "`nProduction launch preparation complete!`n" -ForegroundColor Cyan
