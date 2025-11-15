#!/usr/bin/env python3
"""
MV-CRS Multi-Horizon Predictive Ensemble (MHPE) — Phase XLI

Fuses short-term, mid-term, and long-term governance signals into
1-day, 7-day, and 30-day instability probability forecasts.

Inputs:
  Short-term: policy_fusion_state.json, adaptive_response_history.jsonl
  Mid-term: forensic_forecast.json, mvcrs_feedback.json
  Long-term: mvcrs_long_horizon_plan.json, mvcrs_horizon_coherence.json

Outputs:
  state/mvcrs_multi_horizon_ensemble.json:
    {
      "instability_1d": float,
      "instability_7d": float,
      "instability_30d": float,
      "feature_contributions": {
        "short_term": float,
        "mid_term": float,
        "long_term": float
      },
      "dominant_horizon": "short_term" | "mid_term" | "long_term",
      "ensemble_confidence": float,
      "explanation": str,
      "timestamp": UTC ISO
    }
  logs/mvcrs_mhpe_log.jsonl

Safety:
  - Atomic writes (1s/3s/9s retry)
  - Fix branch: fix/mvcrs-mhpe-<timestamp>
  - Idempotent audit marker: <!-- MVCRS_MHPE: UPDATED <UTC> -->
  - Exit codes: 0 (success), 2 (write failure)

Author: GitHub Copilot
Created: 2025-11-15
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------
# Path Resolution (MVCRS_BASE_DIR virtualization)
# ---------------------------------------------------------------------

def _p(rel: str) -> Path:
    base = os.environ.get("MVCRS_BASE_DIR")
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent.parent / rel


# ---------------------------------------------------------------------
# Loaders with Graceful Fallbacks
# ---------------------------------------------------------------------

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _load_jsonl(path: Path, max_lines: int = 50) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data.append(json.loads(line))
                except Exception:
                    continue
                if len(data) >= max_lines:
                    break
    except Exception:
        return []
    return data


def compute_freshness_factor(timestamp_str: Optional[str], horizon_hours: float) -> float:
    """
    Compute freshness factor based on how recent the data is.
    Returns 1.0 if fresh, decays toward 0.0 as data ages beyond horizon_hours.
    """
    if not timestamp_str:
        return 0.5  # Unknown freshness
    try:
        ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - ts).total_seconds() / 3600  # hours
        if age < 0:
            return 1.0  # Future timestamp (clock skew) - assume fresh
        decay = max(0.0, 1.0 - (age / horizon_hours))
        return decay
    except Exception:
        return 0.5


# ---------------------------------------------------------------------
# Feature Extraction
# ---------------------------------------------------------------------

def extract_short_term_signal(
    fusion: Dict[str, Any],
    adaptive_history: List[Dict[str, Any]]
) -> Tuple[float, float]:
    """
    Extract short-term instability signal and confidence.
    Returns: (instability_score, confidence)
    """
    fusion_state = fusion.get('fusion_state', 'GREEN')
    fusion_map = {'GREEN': 0.1, 'YELLOW': 0.4, 'RED': 0.8}
    fusion_score = fusion_map.get(fusion_state, 0.1)
    
    # Adaptive response intensity
    intervention_count = sum(1 for e in adaptive_history[-10:] 
                            if 'intervene' in str(e.get('action', '')).lower() 
                            or 'lock' in str(e.get('action', '')).lower())
    adaptive_score = min(0.3, intervention_count * 0.1)
    
    # Combined short-term signal
    signal = (fusion_score * 0.7 + adaptive_score * 0.3)
    
    # Confidence based on data presence and freshness
    has_fusion = bool(fusion)
    has_adaptive = len(adaptive_history) > 0
    freshness = compute_freshness_factor(fusion.get('timestamp'), horizon_hours=24)
    
    # Lower confidence when data is missing or stale
    confidence = (0.5 * has_fusion + 0.3 * has_adaptive + 0.2 * freshness)
    if not has_fusion or not has_adaptive:
        confidence *= 0.6  # Penalty for missing data
    
    return signal, confidence


def extract_mid_term_projection(
    forensic: Dict[str, Any],
    feedback: Dict[str, Any]
) -> Tuple[float, float]:
    """
    Extract mid-term (7-10 day) projection and confidence.
    Returns: (projection_score, confidence)
    """
    # Forensic drift probability
    drift_prob = forensic.get('drift_probability', 0.0)
    
    # MV-CRS feedback status
    mvcrs_status = feedback.get('mvcrs_status', 'ok')
    status_map = {'ok': 0.1, 'warning': 0.5, 'failed': 0.85}
    status_score = status_map.get(mvcrs_status, 0.1)
    
    # Combined mid-term projection
    projection = (drift_prob * 0.6 + status_score * 0.4)
    
    # Confidence with boost for high-signal scenarios
    has_forensic = bool(forensic)
    has_feedback = bool(feedback)
    forensic_fresh = compute_freshness_factor(forensic.get('timestamp'), horizon_hours=168)  # 7 days
    feedback_fresh = compute_freshness_factor(feedback.get('timestamp'), horizon_hours=168)
    
    confidence = (0.5 * has_forensic * forensic_fresh + 
                  0.5 * has_feedback * feedback_fresh)
    
    # Boost confidence when both sources present and high signal
    if has_forensic and has_feedback and (drift_prob > 0.6 or mvcrs_status in ['warning', 'failed']):
        confidence = min(1.0, confidence * 1.3)  # Up to 30% boost for high-signal completeness
    
    return projection, confidence


def extract_long_term_outlook(
    hlgs: Dict[str, Any],
    coherence: Dict[str, Any]
) -> Tuple[float, float]:
    """
    Extract long-term (30-45 day) outlook and confidence.
    Returns: (outlook_score, confidence)
    """
    # HLGS status
    hlgs_status = hlgs.get('status', 'stable')
    status_map = {'stable': 0.1, 'volatile': 0.5, 'critical': 0.9}
    hlgs_score = status_map.get(hlgs_status, 0.1)
    
    # HLGS policy instability
    policy_instab = hlgs.get('predicted_policy_instability', 0.0)
    
    # Horizon coherence instability
    coherence_instab = coherence.get('instability_score', 0.0)
    
    # Combined long-term outlook
    outlook = (hlgs_score * 0.5 + policy_instab * 0.3 + coherence_instab * 0.2)
    
    # Confidence with boost for high-signal scenarios
    has_hlgs = bool(hlgs)
    has_coherence = bool(coherence)
    hlgs_conf = hlgs.get('confidence', 0.0)
    coherence_conf = coherence.get('confidence', 0.0)
    hlgs_fresh = compute_freshness_factor(hlgs.get('timestamp'), horizon_hours=720)  # 30 days
    coherence_fresh = compute_freshness_factor(coherence.get('timestamp'), horizon_hours=720)
    
    confidence = (0.4 * has_hlgs * hlgs_conf * hlgs_fresh + 
                  0.6 * has_coherence * coherence_conf * coherence_fresh)
    
    # Boost confidence when both sources present and high signal
    if has_hlgs and has_coherence and (hlgs_status in ['volatile', 'critical'] or policy_instab > 0.6):
        confidence = min(1.0, confidence * 1.4)  # Up to 40% boost for high-signal completeness
    
    return outlook, confidence


# ---------------------------------------------------------------------
# Ensemble Computation
# ---------------------------------------------------------------------

def compute_feature_contributions(
    short_conf: float,
    mid_conf: float,
    long_conf: float
) -> Dict[str, float]:
    """
    Compute normalized feature contributions that sum to 1.0.
    Higher confidence horizons get more weight.
    """
    total = short_conf + mid_conf + long_conf
    if total == 0:
        # Equal weights if no data
        return {
            'short_term': 0.333,
            'mid_term': 0.333,
            'long_term': 0.334
        }
    
    return {
        'short_term': round(short_conf / total, 3),
        'mid_term': round(mid_conf / total, 3),
        'long_term': round(long_conf / total, 3)
    }


def compute_instability_probabilities(
    short_signal: float,
    mid_projection: float,
    long_outlook: float,
    contributions: Dict[str, float]
) -> Dict[str, float]:
    """
    Compute 1d, 7d, 30d instability probabilities.
    Short-term dominates 1d, long-term dominates 30d.
    """
    # 1-day: heavily weighted toward short-term
    instab_1d = (short_signal * 0.70 + 
                 mid_projection * 0.20 + 
                 long_outlook * 0.10)
    
    # 7-day: balanced with mid-term emphasis
    instab_7d = (short_signal * 0.30 + 
                 mid_projection * 0.50 + 
                 long_outlook * 0.20)
    
    # 30-day: long-term dominated
    instab_30d = (short_signal * 0.10 + 
                  mid_projection * 0.30 + 
                  long_outlook * 0.60)
    
    # Apply contribution weighting (agreement bonus/divergence penalty)
    agreement = 1.0 - abs(contributions['short_term'] - contributions['long_term'])
    bonus = agreement * 0.05  # Up to 5% adjustment
    
    # If horizons agree (high agreement), reduce instability slightly (coherent signal)
    # If horizons diverge (low agreement), increase instability (uncertain signal)
    if short_signal < 0.3 and mid_projection < 0.3 and long_outlook < 0.3:
        # All horizons calm → apply bonus (reduce instability)
        instab_1d = max(0.0, instab_1d - bonus)
        instab_7d = max(0.0, instab_7d - bonus)
        instab_30d = max(0.0, instab_30d - bonus)
    elif short_signal > 0.6 or mid_projection > 0.6 or long_outlook > 0.6:
        # Any horizon elevated → apply penalty (increase instability)
        instab_1d = min(1.0, instab_1d + bonus)
        instab_7d = min(1.0, instab_7d + bonus)
        instab_30d = min(1.0, instab_30d + bonus)
    
    return {
        'instability_1d': round(max(0.0, min(1.0, instab_1d)), 3),
        'instability_7d': round(max(0.0, min(1.0, instab_7d)), 3),
        'instability_30d': round(max(0.0, min(1.0, instab_30d)), 3)
    }


def compute_ensemble_confidence(
    short_conf: float,
    mid_conf: float,
    long_conf: float,
    coherence: Dict[str, Any]
) -> float:
    """
    Compute ensemble confidence based on data completeness, coherence alignment, and recency.
    """
    # Data completeness (average of available horizon confidences)
    completeness = (short_conf + mid_conf + long_conf) / 3.0
    
    # Coherence alignment (from HCE)
    coherence_status = coherence.get('coherence_status', 'aligned')
    alignment_map = {'aligned': 1.0, 'tension': 0.7, 'conflict': 0.4}
    alignment = alignment_map.get(coherence_status, 0.7)
    
    # Recency factor (average freshness across horizons)
    # Approximated by confidence values which include freshness weighting
    recency = (short_conf + mid_conf + long_conf) / 3.0
    
    # Combined ensemble confidence
    confidence = completeness * 0.4 + alignment * 0.4 + recency * 0.2
    
    return round(max(0.0, min(1.0, confidence)), 3)


def generate_explanation(
    short_signal: float,
    mid_projection: float,
    long_outlook: float,
    contributions: Dict[str, float],
    dominant: str,
    probs: Dict[str, float]
) -> str:
    """
    Generate human-readable explanation of ensemble reasoning.
    """
    horizon_names = {
        'short_term': 'short-term operational signals',
        'mid_term': 'mid-term drift projections',
        'long_term': 'long-term strategic outlook'
    }
    
    dominant_name = horizon_names.get(dominant, 'unknown horizon')
    dominant_pct = int(contributions[dominant] * 100)
    
    # Risk level classification
    def risk_level(prob: float) -> str:
        if prob < 0.10:
            return 'low'
        elif prob < 0.30:
            return 'moderate'
        elif prob < 0.60:
            return 'elevated'
        else:
            return 'high'
    
    risk_1d = risk_level(probs['instability_1d'])
    risk_7d = risk_level(probs['instability_7d'])
    risk_30d = risk_level(probs['instability_30d'])
    
    explanation = (
        f"Ensemble forecast is dominated by {dominant_name} ({dominant_pct}% contribution). "
        f"1-day instability risk is {risk_1d} ({probs['instability_1d']:.1%}), "
        f"7-day risk is {risk_7d} ({probs['instability_7d']:.1%}), "
        f"and 30-day risk is {risk_30d} ({probs['instability_30d']:.1%}). "
    )
    
    # Add specific insights
    if short_signal > 0.6:
        explanation += "Immediate operational stress detected. "
    if mid_projection > 0.6:
        explanation += "Mid-term drift concerns elevated. "
    if long_outlook > 0.6:
        explanation += "Strategic planning indicates prolonged instability. "
    
    if all(p < 0.15 for p in probs.values()):
        explanation += "All horizons indicate stable governance trajectory."
    elif any(p > 0.6 for p in probs.values()):
        explanation += "Heightened vigilance recommended across multiple time horizons."
    
    return explanation.strip()


# ---------------------------------------------------------------------
# Core Ensemble Builder
# ---------------------------------------------------------------------

def build_multi_horizon_ensemble() -> Dict[str, Any]:
    """Build complete multi-horizon predictive ensemble."""
    # Load inputs
    fusion = _load_json(_p('state/policy_fusion_state.json'))
    adaptive_history = _load_jsonl(_p('state/adaptive_response_history.jsonl'))
    forensic = _load_json(_p('state/forensic_forecast.json'))
    feedback = _load_json(_p('state/mvcrs_feedback.json'))
    hlgs = _load_json(_p('state/mvcrs_long_horizon_plan.json'))
    coherence = _load_json(_p('state/mvcrs_horizon_coherence.json'))
    
    # Extract horizon signals and confidences
    short_signal, short_conf = extract_short_term_signal(fusion, adaptive_history)
    mid_projection, mid_conf = extract_mid_term_projection(forensic, feedback)
    long_outlook, long_conf = extract_long_term_outlook(hlgs, coherence)
    
    # Compute feature contributions
    contributions = compute_feature_contributions(short_conf, mid_conf, long_conf)
    
    # Determine dominant horizon
    dominant = max(contributions.items(), key=lambda x: x[1])[0]
    
    # Compute instability probabilities
    probs = compute_instability_probabilities(
        short_signal, mid_projection, long_outlook, contributions
    )
    
    # Compute ensemble confidence
    ensemble_conf = compute_ensemble_confidence(
        short_conf, mid_conf, long_conf, coherence
    )
    
    # Generate explanation
    explanation = generate_explanation(
        short_signal, mid_projection, long_outlook,
        contributions, dominant, probs
    )
    
    return {
        'instability_1d': probs['instability_1d'],
        'instability_7d': probs['instability_7d'],
        'instability_30d': probs['instability_30d'],
        'feature_contributions': contributions,
        'dominant_horizon': dominant,
        'ensemble_confidence': ensemble_conf,
        'explanation': explanation,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


# ---------------------------------------------------------------------
# Atomic Write Helpers
# ---------------------------------------------------------------------

def write_state(obj: Dict[str, Any]) -> bool:
    """Atomic write with 1s/3s/9s retry."""
    path = _p('state/mvcrs_multi_horizon_ensemble.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    
    for delay in [1, 3, 9]:
        try:
            tmp = path.with_suffix('.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(obj, f, indent=2)
            tmp.replace(path)
            print(f"✓ Wrote ensemble state: {path}")
            return True
        except Exception as e:
            print(f"⚠ Write failure (retry {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    
    print(f"✗ Persistent write failure: {path}", file=sys.stderr)
    return False


def append_log(obj: Dict[str, Any]) -> bool:
    """Append to JSONL log with retry."""
    path = _p('logs/mvcrs_mhpe_log.jsonl')
    path.parent.mkdir(parents=True, exist_ok=True)
    
    for delay in [1, 3, 9]:
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(obj) + '\n')
            print(f"✓ Appended to MHPE log: {path}")
            return True
        except Exception as e:
            print(f"⚠ Log append failure (retry {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    
    print(f"✗ Persistent log append failure: {path}", file=sys.stderr)
    return False


def update_audit_marker(status: str = 'UPDATED') -> None:
    """Update idempotent audit marker in execution summary."""
    summary = _p('INSTRUCTION_EXECUTION_SUMMARY.md')
    if not summary.exists():
        return
    
    marker_prefix = '<!-- MVCRS_MHPE:'
    timestamp = datetime.now(timezone.utc).isoformat()
    new_marker = f"<!-- MVCRS_MHPE: {status} {timestamp} -->"
    
    try:
        content = summary.read_text(encoding='utf-8')
        lines = [line for line in content.split('\n') 
                 if not line.strip().startswith(marker_prefix)]
        lines.append(new_marker)
        
        tmp = summary.with_suffix('.tmp')
        tmp.write_text('\n'.join(lines), encoding='utf-8')
        tmp.replace(summary)
        print(f"✓ Updated audit marker: {status}")
    except Exception as e:
        print(f"⚠ Marker update error: {e}", file=sys.stderr)


def create_fix_branch() -> None:
    """Create fix branch on persistent failure."""
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    branch = f'fix/mvcrs-mhpe-{ts}'
    try:
        import subprocess
        subprocess.run(['git', 'checkout', '-b', branch], check=False)
        print(f"✓ Created fix branch: {branch}")
    except Exception as e:
        print(f"⚠ Fix branch error: {e}", file=sys.stderr)


# ---------------------------------------------------------------------
# Main Orchestration
# ---------------------------------------------------------------------

def run_mhpe_engine() -> int:
    """
    Main multi-horizon predictive ensemble orchestration.
    Returns: 0 (success), 2 (write failure)
    """
    print('=' * 60)
    print('MV-CRS Multi-Horizon Predictive Ensemble — Phase XLI')
    print('=' * 60)
    
    # Build ensemble
    ensemble = build_multi_horizon_ensemble()
    
    print(f"\n1-day instability: {ensemble['instability_1d']:.1%}")
    print(f"7-day instability: {ensemble['instability_7d']:.1%}")
    print(f"30-day instability: {ensemble['instability_30d']:.1%}")
    print(f"Dominant horizon: {ensemble['dominant_horizon']}")
    print(f"Ensemble confidence: {ensemble['ensemble_confidence']:.1%}")
    print(f"\nExplanation: {ensemble['explanation']}")
    
    # Write outputs
    state_ok = write_state(ensemble)
    log_ok = append_log(ensemble)
    
    if not (state_ok and log_ok):
        create_fix_branch()
        update_audit_marker('FAILED')
        return 2
    
    update_audit_marker('UPDATED')
    
    print('\n' + '=' * 60)
    print('✓ Multi-horizon ensemble computation completed')
    print('=' * 60)
    return 0


if __name__ == '__main__':
    sys.exit(run_mhpe_engine())
