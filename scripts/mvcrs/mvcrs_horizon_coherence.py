#!/usr/bin/env python3
"""
MV-CRS Horizon Coherence Engine (HCE) — Phase XL (Instruction 140)

Align short-term, mid-term, and long-term (45-day HLGS) governance outlooks
into a single coherent forecast, preventing contradictory autonomous actions.

Inputs:
  Short-Term:
    - state/adaptive_response_history.jsonl (optional but influences short-term)
    - state/policy_fusion_state.json (mandatory for fusion drift)
  Mid-Term (7–10 day signals):
    - state/forensic_forecast.json
    - state/mvcrs_feedback.json
    - state/mvcrs_strategic_influence.json
  Long-Term (45-day):
    - state/mvcrs_long_horizon_plan.json

Output:
  state/mvcrs_horizon_coherence.json with:
  {
    "coherence_status": "aligned" | "tension" | "conflict",
    "short_term_signal": str,
    "mid_term_projection": str,
    "long_term_outlook": str,
    "conflict_sources": list[str],
    "instability_score": float,
    "governance_alignment_recommendation": "hold" | "stabilize" | "intervene",
    "confidence": float,
    "timestamp": UTC ISO 8601
  }

Safety:
  - Atomic writes (1s,3s,9s retry)
  - Fix-branch on persistent failure: fix/mvcrs-hce-<timestamp>
  - Idempotent audit marker: <!-- MVCRS_HCE: UPDATED <UTC> --> or CONFLICT marker during CI

Author: GitHub Copilot
Created: 2025-11-15
"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

# ---------------------------------------------------------------------
# Path Resolution (MVCRS_BASE_DIR virtualization for tests)
# ---------------------------------------------------------------------

def _p(rel: str) -> Path:
    base = os.environ.get("MVCRS_BASE_DIR")
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent.parent / rel

# ---------------------------------------------------------------------
# Loaders
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
                line=line.strip()
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

# ---------------------------------------------------------------------
# Horizon Signal Extraction
# ---------------------------------------------------------------------

def derive_short_term_signal(adaptive_history: List[Dict[str, Any]], fusion: Dict[str, Any]) -> str:
    """Classify short-term state using recent adaptive response and fusion state."""
    if not adaptive_history:
        # fallback to fusion_state only
        fs = fusion.get('fusion_state', 'GREEN')
        if fs == 'RED':
            return 'intervening'
        if fs == 'YELLOW':
            return 'escalating'
        return 'stable'
    # Count action types if present
    action_counts = {}
    for entry in adaptive_history[-10:]:
        action = entry.get('action') or entry.get('type') or 'unknown'
        action_counts[action] = action_counts.get(action, 0) + 1
    # Heuristic classification
    interventions = sum(v for k,v in action_counts.items() if 'intervene' in k or 'lock' in k)
    escalations = sum(v for k,v in action_counts.items() if 'escalate' in k or 'raise' in k)
    quiet = sum(v for k,v in action_counts.items() if 'monitor' in k or 'observe' in k)
    if interventions >= 2:
        return 'intervening'
    if escalations >= 2:
        return 'escalating'
    if quiet >= 5:
        return 'quiet'
    return 'stable'

def derive_mid_term_projection(forensic: Dict[str, Any], feedback: Dict[str, Any], strategic: Dict[str, Any]) -> str:
    risk = forensic.get('drift_probability', 0.0)
    mv_status = feedback.get('mvcrs_status', strategic.get('mvcrs_health', 'ok'))
    if mv_status == 'failed' or risk > 0.6:
        return 'elevated'
    if mv_status == 'warning' or risk > 0.3:
        return 'watch'
    return 'normal'

def derive_long_term_outlook(hlgs: Dict[str, Any]) -> str:
    status = hlgs.get('status', 'stable')
    if status == 'stable':
        return 'stable'
    if status == 'volatile':
        return 'volatile'
    if status == 'critical':
        return 'critical'
    return 'stable'

# ---------------------------------------------------------------------
# Coherence & Divergence
# ---------------------------------------------------------------------
RISK_SCALE_SHORT = {
    'stable': 0.2,
    'quiet': 0.1,
    'escalating': 0.5,
    'intervening': 0.8
}
RISK_SCALE_MID = {
    'normal': 0.2,
    'watch': 0.5,
    'elevated': 0.85
}
RISK_SCALE_LONG = {
    'stable': 0.2,
    'volatile': 0.55,
    'critical': 0.9
}

def compute_divergence(short_sig: str, mid_proj: str, long_out: str) -> Dict[str, Any]:
    s = RISK_SCALE_SHORT.get(short_sig, 0.2)
    m = RISK_SCALE_MID.get(mid_proj, 0.2)
    l = RISK_SCALE_LONG.get(long_out, 0.2)
    pairs = {
        'short_vs_mid': abs(s - m),
        'short_vs_long': abs(s - l),
        'mid_vs_long': abs(m - l)
    }
    max_diff = max(pairs.values())
    contradictions = [p for p,d in pairs.items() if d >= 0.5]
    # Determine coherence status
    if max_diff < 0.3:
        status = 'aligned'
    elif contradictions and max_diff >= 0.6:
        status = 'conflict'
    elif max_diff >= 0.3:
        status = 'tension'
    else:
        status = 'aligned'
    # Divergence cluster if >=2 contradictions
    cluster = len(contradictions) >= 2
    return {
        'pairwise_diffs': pairs,
        'max_diff': max_diff,
        'contradictions': contradictions,
        'cluster': cluster,
        'coherence_status': status
    }

# ---------------------------------------------------------------------
# Instability Score
# ---------------------------------------------------------------------

def compute_instability(div: Dict[str, Any], forensic: Dict[str, Any], fusion: Dict[str, Any], hlgs: Dict[str, Any]) -> float:
    divergence_weight = div['max_diff']  # 0-~0.8
    forecast_delta = forensic.get('drift_probability', 0.0)  # 0-1
    fusion_state = fusion.get('fusion_state', 'GREEN')
    fusion_drift = {'GREEN': 0.1, 'YELLOW': 0.4, 'RED': 0.75}.get(fusion_state, 0.1)
    # Add long-term policy instability if present
    long_instab = hlgs.get('predicted_policy_instability', 0.0)
    # Adjusted weighting to amplify high-risk scenarios
    score = (divergence_weight * 0.3 +
             forecast_delta * 0.35 +
             fusion_drift * 0.2 +
             long_instab * 0.15)
    # Severe bonus when both forecast and long-term instability are very high
    if forecast_delta > 0.9 and long_instab > 0.9:
        score += 0.1
    return max(0.0, min(1.0, round(score, 3)))

# ---------------------------------------------------------------------
# Governance Alignment Recommendation
# ---------------------------------------------------------------------

def recommend_alignment(coherence_status: str, instability: float, div: Dict[str, Any]) -> str:
    if coherence_status == 'aligned' and instability < 0.4:
        return 'hold'
    if coherence_status == 'tension' or (0.4 <= instability < 0.7):
        return 'stabilize'
    if coherence_status == 'conflict' or instability >= 0.7 or div['cluster']:
        return 'intervene'
    return 'hold'

# ---------------------------------------------------------------------
# Confidence Scoring
# ---------------------------------------------------------------------

def compute_confidence(present_flags: Dict[str, bool], div: Dict[str, Any], hlgs: Dict[str, Any]) -> float:
    completeness = sum(present_flags.values()) / len(present_flags)
    consistency = max(0.0, 1.0 - div['max_diff'])  # higher when horizons close
    hlgs_factor = 1.0 - hlgs.get('predicted_policy_instability', 0.0)  # trust long-term stability
    confidence = completeness * 0.4 + consistency * 0.3 + hlgs_factor * 0.3
    # Penalty for low completeness (<50% of inputs) to reflect uncertainty
    if completeness < 0.5:
        confidence *= 0.75  # reduce by 25%
    return max(0.0, min(1.0, round(confidence, 3)))

# ---------------------------------------------------------------------
# Audit Marker Update (Idempotent)
# ---------------------------------------------------------------------

def update_audit_marker(status: str) -> None:
    summary = _p('INSTRUCTION_EXECUTION_SUMMARY.md')
    if not summary.exists():
        return
    marker_prefix = '<!-- MVCRS_HCE:'
    timestamp = datetime.now(timezone.utc).isoformat()
    new_marker = f"<!-- MVCRS_HCE: {status} {timestamp} -->"
    content = summary.read_text(encoding='utf-8')
    lines = [line for line in content.split('\n') if not line.strip().startswith(marker_prefix)]
    lines.append(new_marker)
    tmp = summary.with_suffix('.tmp')
    tmp.write_text('\n'.join(lines), encoding='utf-8')
    tmp.replace(summary)

# ---------------------------------------------------------------------
# Fix Branch
# ---------------------------------------------------------------------

def create_fix_branch() -> None:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    branch = f'fix/mvcrs-hce-{ts}'
    try:
        import subprocess
        subprocess.run(['git', 'checkout', '-b', branch], check=False)
        print(f"✓ Created fix branch: {branch}")
    except Exception as e:
        print(f"⚠ Fix branch error: {e}", file=sys.stderr)

# ---------------------------------------------------------------------
# Core Build
# ---------------------------------------------------------------------

def build_horizon_coherence() -> Dict[str, Any]:
    adaptive_history = _load_jsonl(_p('state/adaptive_response_history.jsonl'))
    fusion = _load_json(_p('state/policy_fusion_state.json'))
    forensic = _load_json(_p('state/forensic_forecast.json'))
    feedback = _load_json(_p('state/mvcrs_feedback.json'))
    strategic = _load_json(_p('state/mvcrs_strategic_influence.json'))
    hlgs = _load_json(_p('state/mvcrs_long_horizon_plan.json'))

    short_sig = derive_short_term_signal(adaptive_history, fusion)
    mid_proj = derive_mid_term_projection(forensic, feedback, strategic)
    long_out = derive_long_term_outlook(hlgs)

    div = compute_divergence(short_sig, mid_proj, long_out)
    instability = compute_instability(div, forensic, fusion, hlgs)
    recommendation = recommend_alignment(div['coherence_status'], instability, div)

    present_flags = {
        'fusion_state': bool(fusion),
        'forensic_forecast': bool(forensic),
        'feedback': bool(feedback),
        'strategic_influence': bool(strategic),
        'hlgs_plan': bool(hlgs),
        'adaptive_history': bool(adaptive_history)
    }
    confidence = compute_confidence(present_flags, div, hlgs)

    return {
        'coherence_status': div['coherence_status'],
        'short_term_signal': short_sig,
        'mid_term_projection': mid_proj,
        'long_term_outlook': long_out,
        'conflict_sources': div['contradictions'],
        'instability_score': instability,
        'governance_alignment_recommendation': recommendation,
        'confidence': confidence,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

# ---------------------------------------------------------------------
# Atomic Write Helpers
# ---------------------------------------------------------------------

def write_state(obj: Dict[str, Any]) -> bool:
    path = _p('state/mvcrs_horizon_coherence.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    for delay in [1,3,9]:
        try:
            tmp = path.with_suffix('.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(obj, f, indent=2)
            tmp.replace(path)
            print(f"✓ Wrote horizon coherence state: {path}")
            return True
        except Exception as e:
            print(f"⚠ Write failure (retry {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    print("✗ Persistent write failure", file=sys.stderr)
    return False

def append_log(obj: Dict[str, Any]) -> bool:
    path = _p('logs/mvcrs_hce_log.jsonl')
    path.parent.mkdir(parents=True, exist_ok=True)
    for delay in [1,3,9]:
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(obj) + '\n')
            print(f"✓ Appended HCE log: {path}")
            return True
        except Exception as e:
            print(f"⚠ Log append failure (retry {delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    print("✗ Persistent log append failure", file=sys.stderr)
    return False

# ---------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------

def run_hce_engine() -> int:
    print('='*60)
    print('MV-CRS Horizon Coherence Engine — Phase XL')
    print('='*60)

    plan = build_horizon_coherence()

    print(f"Coherence Status: {plan['coherence_status']}")
    print(f"Short-Term: {plan['short_term_signal']} | Mid-Term: {plan['mid_term_projection']} | Long-Term: {plan['long_term_outlook']}")
    print(f"Instability Score: {plan['instability_score']:.3f}")
    print(f"Recommendation: {plan['governance_alignment_recommendation']}")
    print(f"Confidence: {plan['confidence']:.3f}")
    if plan['conflict_sources']:
        print(f"Conflict Sources: {', '.join(plan['conflict_sources'])}")

    state_ok = write_state(plan)
    log_ok = append_log(plan)
    if not (state_ok and log_ok):
        create_fix_branch()
        update_audit_marker('UPDATED')  # still record attempt
        return 2

    update_audit_marker('UPDATED')

    if plan['coherence_status'] == 'conflict' and plan['confidence'] > 0.65:
        # signal elevated attention but non-fatal locally
        return 1

    print('='*60)
    print('[OK] Horizon coherence computation completed')
    print('='*60)
    return 0

if __name__ == '__main__':
    sys.exit(run_hce_engine())
