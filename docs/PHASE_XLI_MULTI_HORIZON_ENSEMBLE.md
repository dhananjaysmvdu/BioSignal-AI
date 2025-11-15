# Phase XLI: Multi-Horizon Predictive Ensemble (MHPE)

**Instruction 141 — MV-CRS Phase XLI**

## Overview

The Multi-Horizon Predictive Ensemble (MHPE) fuses short-term operational signals, mid-term drift projections, and long-term strategic outlooks into unified 1-day, 7-day, and 30-day instability probability forecasts. This phase extends the temporal reconciliation established by Horizon Coherence (Phase XL) to produce probabilistic predictions with provenance tracking, confidence scoring, and human-readable explanations.

MHPE serves as the **predictive cortex** of the MV-CRS governance brain, enabling anticipatory governance interventions across multiple time horizons.

---

## Architecture

### Inputs

The ensemble consumes signals from six primary sources:

| Horizon | Sources | Time Scale |
|---------|---------|------------|
| **Short-term** | `policy_fusion_state.json`, `adaptive_response_history.jsonl` | Hours to 1 day |
| **Mid-term** | `forensic_forecast.json`, `mvcrs_feedback.json` | 7-10 days |
| **Long-term** | `mvcrs_long_horizon_plan.json`, `mvcrs_horizon_coherence.json` | 30-45 days |

Each source provides:
- **Risk signal** (operational state, drift probability, policy instability)
- **Confidence** (data quality, freshness, completeness)
- **Timestamp** (for recency weighting)

### Feature Extraction

#### Short-term Signal Extraction
```python
fusion_state: GREEN/YELLOW/RED → [0.1, 0.4, 0.8]
adaptive_history: intervention_count * 0.1 → [0.0, 0.3]
combined: fusion_score * 0.7 + adaptive_score * 0.3
confidence: data_presence * freshness
```

#### Mid-term Projection Extraction
```python
forensic_drift: drift_probability → [0.0, 1.0]
feedback_status: ok/warning/failed → [0.1, 0.5, 0.85]
combined: drift_prob * 0.6 + status_score * 0.4
confidence: forensic_fresh * 0.5 + feedback_fresh * 0.5
```

#### Long-term Outlook Extraction
```python
hlgs_status: stable/volatile/critical → [0.1, 0.5, 0.9]
policy_instability: predicted_policy_instability → [0.0, 1.0]
coherence_instability: instability_score → [0.0, 1.0]
combined: hlgs * 0.5 + policy * 0.3 + coherence * 0.2
confidence: hlgs_conf * hlgs_fresh * 0.4 + coherence_conf * coherence_fresh * 0.6
```

### Ensemble Computation

#### Instability Probabilities

Three probabilities are computed with horizon-specific weighting:

**1-Day Instability** (short-term dominated):
```
instab_1d = short_signal * 0.70 + mid_projection * 0.20 + long_outlook * 0.10
```

**7-Day Instability** (mid-term emphasis):
```
instab_7d = short_signal * 0.30 + mid_projection * 0.50 + long_outlook * 0.20
```

**30-Day Instability** (long-term dominated):
```
instab_30d = short_signal * 0.10 + mid_projection * 0.30 + long_outlook * 0.60
```

#### Agreement Bonus / Divergence Penalty

Horizon agreement is computed as:
```
agreement = 1.0 - |short_contribution - long_contribution|
bonus = agreement * 0.05
```

- **All horizons calm** (signals < 0.3) → **reduce instability** by up to 5% (coherent stable signal)
- **Any horizon elevated** (signal > 0.6) → **increase instability** by up to 5% (uncertain risk signal)

#### Feature Contributions

Contributions sum to 1.0 and reflect confidence-weighted influence:

```python
total_conf = short_conf + mid_conf + long_conf
short_contribution = short_conf / total_conf
mid_contribution = mid_conf / total_conf
long_contribution = long_conf / total_conf
```

**Dominant horizon**: The contribution with highest weight.

#### Ensemble Confidence

```
completeness = (short_conf + mid_conf + long_conf) / 3.0
alignment = coherence_status_map[aligned=1.0, tension=0.7, conflict=0.4]
recency = (short_conf + mid_conf + long_conf) / 3.0  # Confidence includes freshness weighting
ensemble_confidence = completeness * 0.4 + alignment * 0.4 + recency * 0.2
```

### Explanation Generation

Human-readable explanations are generated following this template:

```
"Ensemble forecast is dominated by {dominant_horizon} ({contribution}% contribution). 
1-day instability risk is {risk_level} ({probability}%), 
7-day risk is {risk_level} ({probability}%), 
and 30-day risk is {risk_level} ({probability}). 
{specific_insights}"
```

**Risk levels**:
- `low`: prob < 0.10
- `moderate`: 0.10 ≤ prob < 0.30
- `elevated`: 0.30 ≤ prob < 0.60
- `high`: prob ≥ 0.60

**Specific insights** triggered by:
- Short signal > 0.6 → "Immediate operational stress detected."
- Mid projection > 0.6 → "Mid-term drift concerns elevated."
- Long outlook > 0.6 → "Strategic planning indicates prolonged instability."
- All probabilities < 0.15 → "All horizons indicate stable governance trajectory."
- Any probability > 0.6 → "Heightened vigilance recommended across multiple time horizons."

---

## Output Schema

```json
{
  "instability_1d": 0.0-1.0,
  "instability_7d": 0.0-1.0,
  "instability_30d": 0.0-1.0,
  "feature_contributions": {
    "short_term": 0.0-1.0,
    "mid_term": 0.0-1.0,
    "long_term": 0.0-1.0
  },
  "dominant_horizon": "short_term" | "mid_term" | "long_term",
  "ensemble_confidence": 0.0-1.0,
  "explanation": "Human-readable explanation paragraph",
  "timestamp": "UTC ISO timestamp"
}
```

Written to: `state/mvcrs_multi_horizon_ensemble.json`  
Log: `logs/mvcrs_mhpe_log.jsonl`

---

## CI Orchestration

### Schedule

**Daily execution: 08:20 UTC**

Runs after Horizon Coherence (08:00 UTC) to leverage latest temporal reconciliation data.

### Workflow Steps

1. **Checkout repository**
2. **Install dependencies** (Python 3.13, requirements.txt)
3. **Run MHPE engine** (`scripts/mhpe/mvcrs_multi_horizon_ensemble.py`)
4. **Evaluate ensemble status**:
   - Failure condition: **Any probability > 0.95 AND ensemble_confidence > 0.70**
   - This indicates high-confidence prediction of critical instability
5. **Upload artifacts** (state JSON, logs) — 90-day retention
6. **Create fix-branch on failure** (`fix/mvcrs-mhpe-<timestamp>`)
7. **Append audit marker** (`<!-- MVCRS_MHPE: VERIFIED/FAILED <UTC> -->`)

### Failure Conditions

| Condition | Action |
|-----------|--------|
| `instability_1d > 0.95 AND confidence > 0.70` | Fail workflow → create fix-branch → append `FAILED` marker |
| `instability_7d > 0.95 AND confidence > 0.70` | Fail workflow → create fix-branch → append `FAILED` marker |
| `instability_30d > 0.95 AND confidence > 0.70` | Fail workflow → create fix-branch → append `FAILED` marker |
| Write failure (exit code 2) | Create fix-branch → exit with code 2 |

---

## Portal Integration

### Predictive Ensemble Card

**Title**: "Predictive Ensemble (1d / 7d / 30d)"

**Header Badge**: Dominant horizon (SHORT-TERM / MID-TERM / LONG-TERM)
- Short-term: Blue (`#3b82f6`)
- Mid-term: Purple (`#8b5cf6`)
- Long-term: Pink (`#ec4899`)

**Display Fields**:

| Field | Badge Colors | Display Format |
|-------|--------------|----------------|
| **1-Day Instability** | Green (<0.10), Yellow (0.10-0.30), Orange (0.30-0.60), Red (>0.60) | `{prob}%` |
| **7-Day Instability** | Green (<0.10), Yellow (0.10-0.30), Orange (0.30-0.60), Red (>0.60) | `{prob}%` |
| **30-Day Instability** | Green (<0.10), Yellow (0.10-0.30), Orange (0.30-0.60), Red (>0.60) | `{prob}%` |
| **Ensemble Confidence** | Meter (low=0.3, high=0.7, optimum=0.9) | `{conf}%` + meter |

**Expandable Explanation**: `<details>` element with full explanation text paragraph.

**Auto-refresh**: Every 15 seconds (same as other MV-CRS cards)

### Color Coding

| Probability Range | Badge Class | Color | Label |
|------------------|-------------|-------|-------|
| < 0.10 | `status-green` | Green (`#10b981`) | LOW |
| 0.10 - 0.30 | Custom | Yellow (`#fbbf24`) | MODERATE |
| 0.30 - 0.60 | Custom | Orange (`#f97316`) | ELEVATED |
| ≥ 0.60 | Custom | Red (`#ef4444`) | HIGH |

---

## Safety Architecture

### Atomic Writes

All file operations use **1s/3s/9s retry pattern**:

```python
for delay in [1, 3, 9]:
    try:
        write_to_tmp_file()
        atomic_replace()
        return True
    except Exception:
        time.sleep(delay)
return False  # Persistent failure
```

### Fix-Branch Creation

On persistent write failure:
1. Create timestamped branch: `fix/mvcrs-mhpe-<YYYYMMDDTHHMMSSZ>`
2. Commit current workspace state
3. Append `<!-- MVCRS_MHPE: FAILED <UTC> -->` marker
4. Exit with code 2

### Audit Marker Idempotency

```python
# Remove all old markers
lines = [line for line in content.split('\n') 
         if not line.strip().startswith('<!-- MVCRS_MHPE:')]
# Append exactly one new marker
lines.append(f'<!-- MVCRS_MHPE: {status} {timestamp} -->')
```

Ensures repeated runs leave **exactly one** `MVCRS_MHPE` marker in `INSTRUCTION_EXECUTION_SUMMARY.md`.

### Deterministic Outputs

- **Stable hashing**: Feature contributions always sum to 1.0 with deterministic rounding
- **Clamping**: All probabilities clamped to [0.0, 1.0]
- **Ordering**: JSON outputs use sorted keys for reproducibility

---

## Test Suite

Located in: `tests/mhpe/test_mhpe_engine.py`

### Test Coverage

| Test | Validation |
|------|------------|
| `test_missing_inputs` | Engine produces probabilities with low confidence when inputs missing |
| `test_aligned_horizons` | All horizons low → probabilities low, confidence higher |
| `test_divergent_horizons` | Mid/long high, short low → 30d elevated, dominant_horizon=mid/long |
| `test_dominant_horizon` | Weights reflect most recent/high-confidence source |
| `test_confidence_clamping` | ensemble_confidence ∈ [0,1], behaves per completeness |
| `test_simulated_write_failure` | Creates fix-branch, returns exit code 2 |
| `test_audit_marker_idempotency` | Repeated runs leave exactly one MVCRS_MHPE marker |

**Additional helper tests**:
- `test_freshness_factor`: Fresh data → high freshness (>0.9); old data → low freshness (<0.5)
- `test_feature_contributions_sum`: Contributions always sum to 1.0
- `test_instability_bounds`: Probabilities clamped to [0, 1] even with out-of-bounds inputs

**Execution**: All 7 main tests + 3 helper tests = **10 tests total**

Run with:
```bash
pytest tests/mhpe -v
```

Expected result: **10 passed**

---

## Phase XLI Achievement

**Instruction 141 Completed**

The Multi-Horizon Predictive Ensemble extends MV-CRS governance from **temporal reconciliation** (Phase XL) to **probabilistic forecasting** (Phase XLI). The system now:

1. **Reconciles horizons** (HCE Phase XL) → prevents contradictory actions
2. **Produces forecasts** (MHPE Phase XLI) → enables anticipatory governance

**Key capabilities**:
- ✅ 1d/7d/30d instability probability forecasts (0.0-1.0)
- ✅ Feature contributions with provenance (short/mid/long sum to 1.0)
- ✅ Dominant horizon detection (highest confidence source)
- ✅ Ensemble confidence scoring (completeness × alignment × recency)
- ✅ Human-readable explanations
- ✅ CI orchestration (08:20 UTC daily, critical instability gating)
- ✅ Portal card (colored badges, confidence meter, expandable explanation)
- ✅ Safety architecture (atomic writes, fix-branch, idempotent markers)
- ✅ Comprehensive test suite (10 tests, all passing)

**Meta-governance expansion**:
- Complete MV-CRS system now spans **Phases XXX-XLI (12 phases total)**
- CI chain extended to **08:20 UTC** (latest daily orchestration step)
- Test coverage: **90 tests total** (83 prior + 7 MHPE main tests)
- Portal cards: **9 total** (including Predictive Ensemble)

**Next evolution**: Phase XLII (if needed) could add multi-variate sensitivity analysis, counterfactual scenario modeling, or real-time horizon re-weighting based on forecast accuracy feedback loops.

---

**Phase XLI — Multi-Horizon Predictive Ensemble: OPERATIONAL**

*The governance brain now forecasts with confidence.*
