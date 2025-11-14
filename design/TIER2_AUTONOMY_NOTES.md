# Tier-2 Autonomy Design Notes

**Phase**: XXVII (Next Phase)  
**Status**: Design / Planning  
**Created**: 2025-11-14

---

## Overview

Tier-2 Autonomy extends Phase XXVI's fusion capabilities with autonomous threshold tuning, enabling the system to self-adjust governance parameters based on historical performance and predictive analytics.

---

## Objectives

1. **Autonomous Threshold Tuning**: Automatically adjust policy thresholds based on system behavior
2. **Drift-Consensus-Forecast Fusion**: Integrate drift detection signals with consensus and forecast risk
3. **Human Approval Gates**: Require manual signoff for critical threshold changes
4. **Adaptive Learning**: Learn optimal thresholds from historical stability patterns

---

## Design Components

### 1. Threshold Tuning Engine

**Purpose**: Analyze historical fusion states and propose threshold adjustments.

**Inputs**:
- `state/policy_fusion_log.jsonl` — Historical fusion decisions
- `state/policy_state_log.jsonl` — Policy orchestration history
- `forensics/forensics_anomaly_forecast.json` — Forecast risk patterns
- `monitoring/drift_detector_state.json` — Drift detection signals
- `federation/weighted_consensus.json` — Consensus stability

**Outputs**:
- `state/threshold_tuning_proposals.json` — Proposed threshold changes
- `state/threshold_tuning_history.jsonl` — Historical tuning decisions

**Proposed Thresholds**:
- Policy RED integrity threshold (current: 90%)
- Policy RED consensus threshold (current: 85%)
- Fusion consensus escalation threshold (current: 92%)
- Response rate limit (current: 10/24h)
- Manual unlock daily limit (current: 3/day)

**Tuning Logic**:
```
IF fusion_level flips > 5 times in 24h:
    → Propose relaxing thresholds (reduce sensitivity)

IF fusion_level = RED for > 48h continuous:
    → Propose tightening thresholds (increase sensitivity)

IF consensus variance > 10% over 7 days:
    → Propose raising consensus escalation threshold

IF drift detected AND forecast_risk = high:
    → Propose temporary threshold freeze (no auto-tuning)

IF manual unlocks = 0 for 30 days:
    → Propose reducing manual unlock limit (safety improvement)
```

---

### 2. Drift-Consensus-Forecast Fusion

**Purpose**: Synthesize drift, consensus, and forecast signals into unified risk assessment.

**Fusion Matrix**:

| Drift | Forecast Risk | Consensus | → Risk Level | Action |
|-------|---------------|-----------|--------------|--------|
| Detected | High | <85% | CRITICAL | Block auto-tuning, alert |
| Detected | Medium | <90% | HIGH | Freeze thresholds, manual review |
| None | High | <92% | MEDIUM | Allow tuning with approval |
| None | Medium | ≥92% | LOW | Allow auto-tuning |
| None | Low | ≥95% | MINIMAL | Aggressive auto-tuning |

**Implementation**:
```python
def compute_drift_fusion(drift_state, forecast_risk, consensus_pct):
    if drift_state == "DETECTED":
        if forecast_risk == "high" and consensus_pct < 85:
            return "CRITICAL"  # Block auto-tuning
        if forecast_risk in ["high", "medium"] and consensus_pct < 90:
            return "HIGH"  # Freeze thresholds
    
    if forecast_risk == "high" and consensus_pct < 92:
        return "MEDIUM"  # Require approval
    
    if forecast_risk == "medium" and consensus_pct >= 92:
        return "LOW"  # Allow with logging
    
    if forecast_risk == "low" and consensus_pct >= 95:
        return "MINIMAL"  # Aggressive tuning allowed
    
    return "MEDIUM"  # Default: require approval
```

---

### 3. Human Approval Gates

**Purpose**: Require manual signoff for critical threshold changes.

**Approval Levels**:

**Auto-Approved** (no human signoff):
- Threshold adjustments < 2% from current value
- Rate limit changes within ±2 responses
- Manual unlock changes within ±1 per day

**Review Required** (human signoff within 24h):
- Threshold adjustments 2-5% from current value
- Rate limit changes 3-5 responses
- Consensus escalation threshold changes

**Critical Approval** (immediate human signoff):
- Threshold adjustments > 5% from current value
- Safety brake thresholds
- Trust guard unlock limits
- Any change when drift_fusion = CRITICAL

**Approval Mechanism**:
- Generate approval request: `approvals/threshold_tuning_<id>.json`
- Create GitHub Issue with threshold change proposal
- Require issue closure with approval label before applying
- Timeout: Auto-reject after 72h if no response

**Approval File Format**:
```json
{
  "approval_id": "uuid",
  "proposed_at": "2025-11-14T12:00:00+00:00",
  "threshold": "policy_red_integrity",
  "current_value": 90.0,
  "proposed_value": 88.0,
  "change_pct": -2.2,
  "justification": "Fusion flips reduced by 40% with relaxed threshold in simulation",
  "approval_level": "review_required",
  "status": "pending",
  "timeout_at": "2025-11-17T12:00:00+00:00"
}
```

---

### 4. Adaptive Learning Model

**Purpose**: Learn optimal thresholds from historical stability patterns.

**Training Data**:
- Fusion state stability windows
- Policy flip frequency vs. threshold values
- Consensus variance patterns
- Response execution success rates
- Manual intervention frequency

**Stability Metrics**:
```
Stability Score = (
    0.4 × (1 - fusion_flip_rate_24h) +
    0.3 × consensus_stability_7d +
    0.2 × response_success_rate_7d +
    0.1 × (1 - manual_intervention_rate_7d)
)

Target: Maximize stability score while maintaining safety
```

**Learning Algorithm** (Placeholder - Phase XXVII Implementation):
1. Collect 30-day sliding window of fusion states
2. Compute stability score for each threshold configuration
3. Identify configurations with stability > 0.85
4. Propose threshold shifts toward high-stability configurations
5. Simulate proposed changes with historical data
6. Generate approval request if simulation passes

---

### 5. Safety Design

**Safety Constraints**:

1. **Threshold Bounds** (hard limits):
   - Policy RED integrity: 80-95%
   - Policy RED consensus: 75-90%
   - Fusion consensus escalation: 85-95%
   - Response rate limit: 5-20 per 24h
   - Manual unlock limit: 1-5 per day

2. **Change Rate Limits**:
   - Maximum 1 threshold change per 24h
   - Maximum 3 threshold changes per 7d
   - No changes during FUSION_RED state
   - No changes when drift_fusion = CRITICAL

3. **Rollback Mechanism**:
   - Automatic rollback if stability score drops > 20% within 48h
   - Manual rollback via approval rejection
   - Undo file generation: `state/threshold_tuning_undo_<id>.json`

4. **Emergency Freeze**:
   - Freeze all auto-tuning if:
     - Manual intervention rate > 50% of auto-tuning attempts
     - Fusion flips > 10 in 24h
     - Drift detected + forecast_risk = high
     - Safety brake engaged for > 24h

---

## Phase XXVII Implementation Plan

### Step 1: Threshold Tuning Engine
- Create `scripts/autonomy/threshold_tuning_engine.py`
- Implement proposal generation logic
- Add simulation mode with historical data replay

### Step 2: Drift-Consensus-Forecast Fusion
- Create `scripts/autonomy/drift_fusion_engine.py`
- Integrate drift detector signals
- Implement fusion matrix logic

### Step 3: Approval Gate System
- Create `scripts/autonomy/approval_manager.py`
- Implement GitHub Issue integration
- Add timeout and auto-reject logic

### Step 4: Adaptive Learning
- Create `scripts/autonomy/adaptive_learner.py`
- Implement stability score calculation
- Add sliding window analysis

### Step 5: Safety Monitoring
- Create `scripts/autonomy/safety_monitor.py`
- Implement emergency freeze logic
- Add rollback mechanism

### Step 6: Integration
- Add CI workflows for tuning proposals
- Portal dashboard for approval status
- Regression tests (target: 20+ tests)

---

## Risk Assessment

### High Risk Areas:
- Threshold tuning causing instability oscillations
- Approval timeout leading to missed critical changes
- Learning algorithm converging to suboptimal local minima

### Mitigation Strategies:
- Conservative initial bounds (±2% only)
- Short approval timeouts (24h review, 72h critical)
- Simulation validation before proposal
- Emergency freeze with manual override

---

## Success Metrics

**Phase XXVII Success Criteria**:
- Stability score > 0.85 maintained for 30 days
- Fusion flip rate reduced by > 30%
- Manual intervention rate < 10% of total operations
- Zero threshold-related incidents
- Approval turnaround time < 12h (median)

---

## Open Questions

1. Should threshold tuning be enabled by default or require opt-in?
2. What is the minimum observation period before proposing changes? (30 days? 60 days?)
3. How to handle conflicting proposals (e.g., relax integrity vs. tighten consensus)?
4. Should emergency freeze require manual reset or auto-clear after conditions resolve?
5. Integration with external monitoring systems (e.g., PagerDuty, Slack)?

---

## References

- Phase XXVI: Policy Fusion Engine (foundation for tier-2 autonomy)
- Phase XXV: Policy Orchestration & Response Automation
- Drift Detector: `monitoring/drift_detector.py`
- Forecast Risk: `forensics/forensics_anomaly_forecast.json`
- Consensus: `federation/weighted_consensus.json`

---

**Status**: ✅ DESIGN COMPLETE  
**Next Phase**: XXVII - Autonomous Threshold Tuning Implementation  
**Target Start**: After Phase XXVI operational stabilization (14+ days)

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-14  
**Author**: Autonomous Development System
