#!/usr/bin/env python3
"""
MV-CRS Governance Drift Auditor (GDA) — Phase XLII

Analyzes 90-day governance behavior to quantify long-term drift between expected model-driven trajectory
(MHPE + Horizon Coherence + strategic influence) and observed actions (policy fusion state history,
adaptive responses, escalation patterns).

Outputs:
  state/mvcrs_governance_drift.json
  logs/mvcrs_gda_log.jsonl (append-only)
  Idempotent audit marker in INSTRUCTION_EXECUTION_SUMMARY.md:
    <!-- MVCRS_GDA: UPDATED <UTC ISO> -->

Exit codes:
  0 success
  2 persistent write failure (fix branch created)

Drift Components (each ∈ [0,1]):
  stability_loss   - expected calm vs observed elevated aggressive behavior
  volatility_cycle - frequent oscillations in policy fusion state over time
  stubbornness     - expected high risk but lack of interventions OR expected low risk yet constant high policy level
  overcorrection   - rapid alternating intervention / monitor pattern producing unstable corrective swings

Drift Score:
  drift_score = clamp( 0.25*(stability_loss + volatility_cycle + stubbornness + overcorrection) )
  drift_direction = component with highest value (ties broken by deterministic name ordering)
  drift_class thresholds: <0.35 low, <0.65 moderate, else high

Confidence:
  availability × stability × alignment
    availability = fraction of primary sources present
    stability = 1 - volatility_cycle
    alignment = 1 - abs(expected_mean - observed_mean) (clamped ≥0)

Contributing Factors:
  Top up to 5 explanatory strings ranked by component magnitudes (deterministic ordering)

Author: GitHub Copilot
Created: 2025-11-15
"""
from __future__ import annotations
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ------------------------------------------------------------
# Path helpers (MVCRS_BASE_DIR virtualization for tests)
# ------------------------------------------------------------

def _p(rel: str) -> Path:
    base = os.environ.get("MVCRS_BASE_DIR")
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent.parent / rel

# ------------------------------------------------------------
# Safe JSON/JSONL loaders
# ------------------------------------------------------------

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _load_jsonl(path: Path, max_days: int = 90) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data: List[Dict[str, Any]] = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                data.append(obj)
    except Exception:
        return []
    # Filter last 90 days if timestamp present
    now = datetime.now(timezone.utc)
    filtered: List[Dict[str, Any]] = []
    for obj in data[::-1]:  # iterate backward (recent first)
        ts_str = obj.get('timestamp')
        if not ts_str:
            filtered.append(obj)
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        except Exception:
            filtered.append(obj)
            continue
        if (now - ts).days <= 90:
            filtered.append(obj)
        if len(filtered) >= 5000:  # safety clamp
            break
    return filtered[::-1]

# ------------------------------------------------------------
# Component Computation
# ------------------------------------------------------------

def map_fusion_state(state: str) -> float:
    mapping = {'GREEN': 0.1, 'YELLOW': 0.5, 'RED': 0.9}
    return mapping.get(state.upper(), 0.1)


def compute_expected_series(mhpe: Dict[str, Any], hce: Dict[str, Any], strategic: Dict[str, Any]) -> List[float]:
    """Build synthetic expected trajectory (length N) from available signals.
    Since we may not have full 90-day probability history, we replicate latest snapshot across window.
    Tests can inject custom sequences by writing mhpe['synthetic_expected_series'].
    """
    if 'synthetic_expected_series' in mhpe and isinstance(mhpe['synthetic_expected_series'], list):
        seq = [float(x) for x in mhpe['synthetic_expected_series'][:500]]
        return seq
    inst1 = float(mhpe.get('instability_1d', 0.0))
    inst7 = float(mhpe.get('instability_7d', inst1))
    inst30 = float(mhpe.get('instability_30d', inst7))
    hce_inst = float(hce.get('instability_score', inst7))
    strategic_risk = float(strategic.get('strategic_risk', inst30)) if strategic else inst30
    base = (inst1 * 0.5 + inst7 * 0.25 + inst30 * 0.15 + hce_inst * 0.1) * (0.7 + 0.3 * strategic_risk)
    # replicate 90 data points (one per day) for simplicity
    return [max(0.0, min(1.0, base)) for _ in range(90)]


def extract_observed_series(fusion_history: List[Dict[str, Any]], adaptive: List[Dict[str, Any]]) -> Tuple[List[float], Dict[str, Any]]:
    """Convert history to observed numeric trajectory + action stats."""
    fusion_levels: List[float] = []
    transitions = 0
    prev = None
    for rec in fusion_history:
        state = rec.get('fusion_state') or rec.get('state') or 'GREEN'
        lvl = map_fusion_state(state)
        fusion_levels.append(lvl)
        if prev is not None and prev != state:
            transitions += 1
        prev = state
    if not fusion_levels and fusion_history:
        fusion_levels = [map_fusion_state(fusion_history[-1].get('fusion_state', 'GREEN'))]
    # Adaptive interventions
    interventions = sum(1 for e in adaptive if 'intervene' in str(e.get('action','')).lower())
    oscillating_pattern = 0
    last_action = None
    for e in adaptive:
        act = str(e.get('action','')).lower()
        if last_action and ((('intervene' in act and 'monitor' in last_action) or ('monitor' in act and 'intervene' in last_action))):
            oscillating_pattern += 1
        last_action = act
    stats = {
        'transitions': transitions,
        'interventions': interventions,
        'oscillations': oscillating_pattern,
        'length': len(fusion_levels)
    }
    return fusion_levels, stats


def compute_components(expected: List[float], observed: List[float], stats: Dict[str, Any], adaptive: List[Dict[str, Any]]) -> Dict[str, float]:
    if not expected or not observed:
        return {k: 0.0 for k in ['stability_loss','volatility_cycle','stubbornness','overcorrection']}
    exp_mean = sum(expected)/len(expected)
    obs_mean = sum(observed)/len(observed)
    # stability_loss: expected calm (<0.3) vs observed elevated (>0.6)
    stability_loss = 0.0
    if exp_mean < 0.3 and obs_mean > 0.6:
        stability_loss = min(1.0, (obs_mean - 0.6) * 1.5)
    # volatility_cycle: transitions normalized by length
    volatility_cycle = min(1.0, stats.get('transitions',0) / max(1, stats.get('length',1)) * 2.0)
    # stubbornness: expected high risk (>0.6) but few interventions OR expected low risk (<0.3) but high constant policy
    interventions = stats.get('interventions',0)
    if exp_mean > 0.6 and interventions == 0:
        stubbornness = min(1.0, (exp_mean - 0.6) * 1.5 + 0.4)
    elif exp_mean < 0.3 and obs_mean > 0.6:
        stubbornness = min(1.0, (obs_mean - 0.6) * 1.5 + 0.3)
    else:
        stubbornness = 0.0
    # overcorrection: oscillations relative to interventions / length
    oscillations = stats.get('oscillations',0)
    overcorrection = min(1.0, oscillations / max(1, interventions + 1) * 1.2)
    return {
        'stability_loss': round(stability_loss,4),
        'volatility_cycle': round(volatility_cycle,4),
        'stubbornness': round(stubbornness,4),
        'overcorrection': round(overcorrection,4)
    }


def compute_drift_score(components: Dict[str,float]) -> float:
    score = 0.25 * sum(components.values())
    return round(max(0.0, min(1.0, score)),4)


def classify_drift(score: float) -> str:
    if score < 0.35:
        return 'low'
    if score < 0.65:
        return 'moderate'
    return 'high'


def determine_direction(components: Dict[str,float]) -> str:
    # deterministic tie-breaking by sorted key name
    items = sorted(components.items(), key=lambda x: (-x[1], x[0]))
    return items[0][0] if items else 'unknown'


def build_contributing_factors(components: Dict[str,float], expected_mean: float, observed_mean: float, stats: Dict[str,Any]) -> List[str]:
    factors: List[Tuple[str,float]] = []
    if components['stability_loss']>0:
        factors.append((f"stability_loss(exp={expected_mean:.2f},obs={observed_mean:.2f})", components['stability_loss']))
    if components['volatility_cycle']>0:
        factors.append((f"volatility(transitions={stats.get('transitions',0)})", components['volatility_cycle']))
    if components['stubbornness']>0:
        factors.append((f"stubbornness(actions={stats.get('interventions',0)})", components['stubbornness']))
    if components['overcorrection']>0:
        factors.append((f"overcorrection(oscillations={stats.get('oscillations',0)})", components['overcorrection']))
    # add alignment delta
    delta = abs(expected_mean - observed_mean)
    factors.append((f"alignment_delta({delta:.2f})", min(1.0, delta)))
    # deterministic sort
    factors_sorted = sorted(factors, key=lambda x: (-x[1], x[0]))
    return [f[0] for f in factors_sorted[:5]]


def compute_confidence(sources_present: Dict[str,bool], components: Dict[str,float], expected_mean: float, observed_mean: float) -> float:
    availability = sum(1 for v in sources_present.values() if v) / max(1,len(sources_present))
    stability = 1 - components.get('volatility_cycle',0.0)
    alignment = max(0.0, 1 - abs(expected_mean - observed_mean))
    conf = availability * stability * alignment
    return round(max(0.0, min(1.0, conf)),4)

# ------------------------------------------------------------
# Atomic persistence helpers
# ------------------------------------------------------------

def atomic_write(path: Path, obj: Dict[str,Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    for delay in [1,3,9]:
        try:
            tmp = path.with_suffix('.tmp')
            with open(tmp,'w',encoding='utf-8') as f:
                json.dump(obj,f,indent=2,sort_keys=True)
            tmp.replace(path)
            return True
        except Exception as e:
            print(f"⚠ write retry ({delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    print(f"✗ persistent write failure: {path}", file=sys.stderr)
    return False


def append_log(path: Path, obj: Dict[str,Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    for delay in [1,3,9]:
        try:
            with open(path,'a',encoding='utf-8') as f:
                f.write(json.dumps(obj,sort_keys=True)+"\n")
            return True
        except Exception as e:
            print(f"⚠ log retry ({delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    print(f"✗ persistent log failure: {path}", file=sys.stderr)
    return False


def update_audit_marker(status: str='UPDATED') -> None:
    summary = _p('INSTRUCTION_EXECUTION_SUMMARY.md')
    if not summary.exists():
        return
    marker_prefix = '<!-- MVCRS_GDA:'
    ts = datetime.now(timezone.utc).isoformat()
    new_marker = f"<!-- MVCRS_GDA: {status} {ts} -->"
    try:
        content = summary.read_text(encoding='utf-8')
        lines = [ln for ln in content.split('\n') if not ln.strip().startswith(marker_prefix)]
        lines.append(new_marker)
        tmp = summary.with_suffix('.tmp')
        tmp.write_text('\n'.join(lines), encoding='utf-8')
        tmp.replace(summary)
    except Exception as e:
        print(f"⚠ marker update error: {e}", file=sys.stderr)


def create_fix_branch() -> None:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    branch = f'fix/mvcrs-gda-{ts}'
    try:
        import subprocess
        subprocess.run(['git','checkout','-b',branch],check=False)
        print(f"✓ created fix branch: {branch}")
    except Exception as e:
        print(f"⚠ fix branch error: {e}", file=sys.stderr)

# ------------------------------------------------------------
# Core auditor logic
# ------------------------------------------------------------

def build_governance_drift() -> Dict[str,Any]:
    # Load sources
    fusion_current = _load_json(_p('state/policy_fusion_state.json'))
    # attempt to load historical fusion; fallback to log file if exists
    fusion_log = _load_jsonl(_p('logs/policy_fusion_state_log.jsonl'))
    if not fusion_log and fusion_current:
        # synthesize simple history for evaluation (single entry replicated)
        fusion_log = [{"fusion_state": fusion_current.get('fusion_state','GREEN'), "timestamp": fusion_current.get('timestamp')}] * 30

    adaptive_history = _load_jsonl(_p('state/adaptive_response_history.jsonl'))
    feedback = _load_json(_p('state/mvcrs_feedback.json'))
    strategic = _load_json(_p('state/mvcrs_strategic_influence.json'))
    coherence = _load_json(_p('state/mvcrs_horizon_coherence.json'))
    mhpe = _load_json(_p('state/mvcrs_multi_horizon_ensemble.json'))

    sources_present = {
        'fusion': bool(fusion_log),
        'adaptive': bool(adaptive_history),
        'feedback': bool(feedback),
        'strategic': bool(strategic),
        'coherence': bool(coherence),
        'mhpe': bool(mhpe)
    }

    expected_series = compute_expected_series(mhpe, coherence, strategic)
    observed_series, stats = extract_observed_series(fusion_log, adaptive_history)

    components = compute_components(expected_series, observed_series, stats, adaptive_history)
    drift_score = compute_drift_score(components)
    direction = determine_direction(components)
    drift_class = classify_drift(drift_score)

    exp_mean = round(sum(expected_series)/len(expected_series),4) if expected_series else 0.0
    obs_mean = round(sum(observed_series)/len(observed_series),4) if observed_series else 0.0

    factors = build_contributing_factors(components, exp_mean, obs_mean, stats)
    confidence = compute_confidence(sources_present, components, exp_mean, obs_mean)

    return {
        'drift_score': drift_score,
        'drift_direction': direction,
        'drift_class': drift_class,
        'components': components,
        'expected_mean': exp_mean,
        'observed_mean': obs_mean,
        'contributing_factors': factors,
        'confidence': confidence,
        'stats': stats,
        'sources_present': sources_present,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

# ------------------------------------------------------------
# Engine runner
# ------------------------------------------------------------

def run_gda_engine() -> int:
    print('='*62)
    print('MV-CRS Governance Drift Auditor — Phase XLII')
    print('='*62)
    result = build_governance_drift()
    print(f"Drift Score: {result['drift_score']:.2f} | Direction: {result['drift_direction']} | Class: {result['drift_class']}")
    print(f"Confidence: {result['confidence']:.2f} | Factors: {', '.join(result['contributing_factors'])}")
    state_ok = atomic_write(_p('state/mvcrs_governance_drift.json'), result)
    log_ok = append_log(_p('logs/mvcrs_gda_log.jsonl'), result)
    if not (state_ok and log_ok):
        create_fix_branch()
        update_audit_marker('FAILED')
        return 2
    update_audit_marker('UPDATED')
    print('✓ Governance drift audit completed')
    return 0

if __name__ == '__main__':
    sys.exit(run_gda_engine())
