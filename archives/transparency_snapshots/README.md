# Transparency Snapshots Archive

This directory contains weekly snapshots of `GOVERNANCE_TRANSPARENCY.md`, captured every Sunday at 03:00 UTC by the `governance_transparency_manifest.yml` workflow.

## Purpose

Weekly snapshots create an **immutable time series** of governance health states, enabling:

1. **Longitudinal Analysis**: Track integrity score trends, artifact availability, and audit marker evolution over months
2. **Forensic Investigation**: Reference historical states when investigating governance anomalies
3. **Compliance Audits**: Provide timestamped evidence of continuous governance monitoring
4. **Research Reproducibility**: Link publications to specific governance snapshots via date

## Naming Convention

Snapshots are named: `YYYY-MM-DD.md`

Example: `2025-11-17.md` (Sunday, November 17, 2025)

## Snapshot Schema

Each snapshot is a complete copy of `GOVERNANCE_TRANSPARENCY.md` at the time of archival, including:

- **Artifacts Table**: Status, timestamps, sizes of 11 governance files
- **Registry Tail**: Last 10 integrity metrics entries
- **Audit Markers Snapshot**: All governance markers (REFLEX_INTEGRITY, SCHEMA_PROVENANCE, etc.)
- **Data Schema**: Canonical field definitions + SHA-256 hash
- **API Endpoints**: Badge JSON and ledger JSONL paths
- **Citation Block**: DOI and research export artifacts

## Workflow Integration

The archival step runs conditionally in `governance_transparency_manifest.yml`:

```yaml
- name: Archive Weekly Transparency Snapshots
  run: |
    # Archive only on Sundays (ISO week day 7)
    if [ "$(date +%u)" = "7" ]; then
      mkdir -p archives/transparency_snapshots
      snapshot_date=$(date +'%Y-%m-%d')
      cp GOVERNANCE_TRANSPARENCY.md "archives/transparency_snapshots/${snapshot_date}.md"
      git add archives/transparency_snapshots/
      git commit -m "docs: archive weekly transparency snapshot (${snapshot_date})"
      git push
    fi
```

## Querying Snapshots

**Find integrity score on specific date:**
```bash
grep "Integrity Score" archives/transparency_snapshots/2025-11-17.md
```

**Compare two snapshots:**
```bash
diff archives/transparency_snapshots/2025-11-10.md archives/transparency_snapshots/2025-11-17.md
```

**Count total violations over time:**
```bash
for file in archives/transparency_snapshots/*.md; do
  echo "$file: $(grep -c "violations" "$file")"
done
```

## Retention Policy

Snapshots are retained indefinitely as part of the Git repository history. Each snapshot adds ~10-20 KB to the repository (text-based Markdown).

If repository size becomes a concern (>1000 snapshots), consider:
1. **Git LFS** for large archives
2. **External archival** to Zenodo via GitHub Releases
3. **Compression** of snapshots older than 1 year

## Integration with Research Outputs

When citing governance states in publications, reference the specific snapshot date:

> "System integrity was validated on 2025-11-17 via archived transparency snapshot (mean integrity score: 97%). See: `archives/transparency_snapshots/2025-11-17.md`"

## License

Snapshot archives are covered by the same license as the parent repository (MIT). Attribution should reference both the repository and the specific snapshot date.

---

**Auto-generated weekly via:** `.github/workflows/governance_transparency_manifest.yml`  
**First snapshot date:** (pending first Sunday execution)  
**Current snapshot count:** (updated dynamically by workflow)
