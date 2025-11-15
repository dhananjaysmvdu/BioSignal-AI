# Phase XL: MV-CRS Horizon Coherence Engine (HCE)

**Instruction 140 — Governance Horizon Reconciliation**

The Horizon Coherence Engine (HCE) aligns short-term operational signals, mid-term risk projections, and long-term strategic planning into a single coherent governance narrative. This prevents autonomous subsystems from acting on contradictory temporal directives.

---
## 1. Three-Horizon Model

| Horizon      | Source Artifacts                                  | Temporal Span | Purpose                                 |
|--------------|----------------------------------------------------|---------------|------------------------------------------|
| Short-Term   | `adaptive_response_history.jsonl`, `policy_fusion_state.json` | Hours–1 day   | Operational intervention & reactive bias |
| Mid-Term     | `forensic_forecast.json`, `mvcrs_feedback.json`, `mvcrs_strategic_influence.json` | 7–10 days     | Emerging drifts & governance posture     |
| Long-Term    | `mvcrs_long_horizon_plan.json`                     | 30–45 days    | Strategic planning & risk projection     |

The engine normalizes each horizon into semantic categories:
- Short-Term: `stable`, `quiet`, `escalating`, `intervening`
- Mid-Term: `normal`, `watch`, `elevated`
- Long-Term: `stable`, `volatile`, `critical`

Each category maps to a numeric risk anchor used for divergence detection.

---
## 2. Divergence Classification

Pairwise horizon comparisons generate risk deltas:
```
short_vs_mid = |short_risk - mid_risk|
short_vs_long = |short_risk - long_risk|
mid_vs_long   = |mid_risk - long_risk|
```

| Max Delta | Contradictions >=2? | Coherence Status |
|-----------|---------------------|------------------|
| < 0.30    | N/A                 | aligned          |
| 0.30–0.59 | < 2 contradictions  | tension          |
| ≥ 0.60    | any contradiction   | conflict         |
| ≥ 0.50    | ≥ 2 contradictions  | conflict (cluster escalation) |

“Contradictions” are pairwise deltas ≥ 0.50. A divergence cluster is detected when two or more contradictions occur simultaneously.

---
## 3. Instability Metric

The instability metric blends four dimensions:
```
divergence_weight = max(pairwise_diffs)
forecast_delta    = forensic.drift_probability
fusion_drift      = map(fusion_state): GREEN→0.1, YELLOW→0.4, RED→0.75
long_instability  = hlgs.predicted_policy_instability

instability = (divergence_weight * 0.3
               + forecast_delta * 0.35
               + fusion_drift * 0.2
               + long_instability * 0.15
               + severe_bonus)

if forecast_delta > 0.9 and long_instability > 0.9:
    severe_bonus = 0.10
else:
    severe_bonus = 0.0
```
All values clamped to `[0.0, 1.0]`.

Interpretation:
- `< 0.40`: Stable multi-horizon environment
- `0.40–0.69`: Emerging instability → stabilization required
- `≥ 0.70`: High volatility → intervention required

---
## 4. Governance Alignment Recommendations

| Coherence Status | Instability Range | Recommendation |
|------------------|-------------------|----------------|
| aligned          | < 0.40            | `hold`         |
| tension          | any               | `stabilize`    |
| conflict         | any               | `intervene`    |
| any              | ≥ 0.70 instability| `intervene`    |
| divergence cluster (≥2 contradictions) | any        | `intervene`    |

Recommendations feed downstream orchestration (threshold adjustments, policy fusion sensitivity, oversight scheduling).

---
## 5. Confidence Scoring

Confidence integrates completeness, temporal consistency, and strategic stability:
```
completeness = present_inputs / 6
consistency = 1 - max_diff
hlgs_factor = 1 - hlgs.predicted_policy_instability
raw_confidence = completeness*0.4 + consistency*0.3 + hlgs_factor*0.3
if completeness < 0.5:
    raw_confidence *= 0.75
confidence = clamp(raw_confidence, 0.0, 1.0)
```

Interpretation:
- `> 0.75`: High coherence trust
- `0.55–0.75`: Moderate—monitor
- `< 0.55`: Low—human validation recommended

Conflict escalation only triggers CI failure when `coherence_status = conflict` AND `confidence > 0.65`.

---
## 6. Output Schema

`state/mvcrs_horizon_coherence.json`:
```json
{
  "coherence_status": "aligned",
  "short_term_signal": "stable",
  "mid_term_projection": "normal",
  "long_term_outlook": "stable",
  "conflict_sources": [],
  "instability_score": 0.028,
  "governance_alignment_recommendation": "hold",
  "confidence": 0.718,
  "timestamp": "2025-11-15T08:00:00Z"
}
```

---
## 7. CI Orchestration

Workflow: `.github/workflows/mvcrs_horizon_coherence.yml`
- **Schedule:** Daily at 08:00 UTC (after HLGS 07:45 UTC)
- **Artifacts:** State + append-only log (90-day retention)
- **Failure Condition:** `coherence_status=conflict` AND `confidence>0.65`
- **Fix Branch:** `fix/mvcrs-hce-<timestamp>` created on conflict or write failure
- **Markers:**
  - Success: `<!-- MVCRS_HCE: VERIFIED <UTC> -->`
  - Conflict: `<!-- MVCRS_HCE: CONFLICT <UTC> -->`
  - Local engine always maintains idempotent `<!-- MVCRS_HCE: UPDATED <UTC> -->`

---
## 8. Safety Model

| Mechanism                | Description                                    |
|--------------------------|------------------------------------------------|
| Atomic Writes            | Temp file + 1s/3s/9s retry                     |
| Fix Branch               | Created on persistent failures/conflicts       |
| Idempotent Audit Marker  | Old markers pruned before appending            |
| Numeric Clamping         | Instability & confidence forced into [0,1]     |
| Confidence Gating        | Prevents over-escalation at low certainty      |
| MVCRS_BASE_DIR Support   | Test virtualization of file system             |

---
## 9. Portal UX & Semantics

“Horizon Coherence (Short / Mid / Long)” card fields:
- **Status Badge:** ALIGNED (green) | TENSION (yellow) | CONFLICT (red)
- **Short-Term Signal:** Operational posture (stable/escalating/intervening)
- **Mid-Term Projection:** Drift/emergence classification (normal/watch/elevated)
- **Long-Term Outlook:** Strategic risk (stable/volatile/critical)
- **Conflict Sources:** Pairwise divergence sources or `NONE`
- **Instability Score:** Percentage scale (0–100%) aggregate risk
- **Alignment Recommendation:** `hold` | `stabilize` | `intervene`
- **Confidence:** Normalized trust score
- **Last Updated:** Localized timestamp

Auto-refresh interval: 15 seconds. Inline styling matches existing portal pattern for visual consistency.

---
## 10. Test Suite Summary

File: `tests/mvcrs/test_hce_engine.py`

| Test                                   | Purpose                                        |
|----------------------------------------|------------------------------------------------|
| `test_perfect_alignment`              | Validates aligned state classification         |
| `test_soft_contradictions_tension`    | Detects tension status                         |
| `test_hard_contradictions_conflict`   | Ensures strong contradictions → conflict       |
| `test_divergence_cluster_detection`   | Cluster (≥2 contradictions) drives intervene   |
| `test_instability_score_bounds`       | High-risk scenario pushes instability ≥0.7     |
| `test_confidence_missing_optional`    | Confidence reduction with incomplete inputs    |
| `test_fix_branch_on_persistent_failure` | Simulates atomic write failure path          |
| `test_idempotent_audit_marker`        | Ensures only one UPDATED marker persists       |

Execution: `pytest tests/mvcrs/test_hce_engine.py -v` → 8 passed.

---
## 11. Phase Achievement

- ✅ Multi-horizon reconciliation engine (`mvcrs_horizon_coherence.py`)
- ✅ Divergence & cluster detection model
- ✅ Instability + confidence scoring framework
- ✅ CI workflow (08:00 UTC) with conflict gating
- ✅ Portal integration (coherence dashboard card)
- ✅ 8 deterministic tests (all passing)
- ✅ Documentation & execution summary update

**Result:** Governance brain now self-reconciles across temporal layers, eliminating contradictory autonomous actions and enabling coherent longitudinal decision-making.

---
**Author:** GitHub Copilot  
**Created:** 2025-11-15  
**Version Target:** v2.14.0-mvcrs-horizon-coherence  
**Status:** Ready for release
