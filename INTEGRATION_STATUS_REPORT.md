# Integration Status Report

**Last Updated**: 2025-11-13T15:40:00+00:00
**Status**: ⏸️ **READY (TOKEN NOT CONFIGURED)**

## Zenodo Integration

**Status**: ⏸️ Configured but awaiting access token  
**DOI**: 10.5281/zenodo.14173152  
**Concept DOI**: 10.5281/zenodo.14173151  
**Sync Frequency**: Weekly (Monday 05:00 UTC)

### Configuration
- ✅ API reference documented
- ✅ Sync config defined
- ✅ Workflow created
- ⏸️ Access token pending (requires GitHub Secret: ZENODO_ACCESS_TOKEN)

### Artifacts to Sync
- Reproducibility capsule (weekly)
- Governance whitepaper
- Capsule manifest with checksums

## GitHub Data Integration

**Status**: ✅ **ACTIVE**  
**Repository**: dhananjaysmvdu/BioSignal-AI  
**Sync**: Continuous (on push to main)

### Tracked Artifacts
- Integrity metrics registry
- Reproducibility trends
- Policy evolution data
- Observatory metrics
- Long-term storage archives

## OpenAIRE Integration

**Status**: 📅 **PLANNED FOR Q2 2026**  
**Target Date**: 2026-04-01

### Planned Features
- Automatic DOI registration with OpenAIRE graph
- Link governance artifacts to EU research projects
- Enable FAIR data discovery

## API Endpoints

All endpoints publicly accessible via GitHub raw content URLs:

- **Metrics JSON**: `/portal/metrics.json`
- **Integrity Registry**: `/exports/integrity_metrics_registry.csv`
- **Schema Provenance**: `/exports/schema_provenance_ledger.jsonl`
- **Observatory Trends**: `/observatory/metrics/`

## Next Steps

1. **Zenodo Token**: Add ZENODO_ACCESS_TOKEN to GitHub repository secrets
2. **Test Sync**: Run manual workflow dispatch to verify Zenodo upload
3. **OpenAIRE Planning**: Research institutional affiliation requirements (Q1 2026)

## Contact

**Maintainer**: Mrityunjay Dhananjay  
**Repository**: https://github.com/dhananjaysmvdu/BioSignal-AI  
**Issues**: https://github.com/dhananjaysmvdu/BioSignal-AI/issues

---

*Integration workflow runs weekly on Monday at 05:00 UTC. Zenodo sync will activate once access token is configured.*
