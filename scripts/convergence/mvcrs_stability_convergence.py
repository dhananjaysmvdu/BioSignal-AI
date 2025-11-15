#!/usr/bin/env python3
"""
MV-CRS Stability Convergence Analysis Engine — Phase XLIV

Computes cross-system stability convergence by weighted agreement across
governance drift, horizon coherence, multi-horizon ensemble, and RDGL policy signals.

Outputs:
  state/mvcrs_stability_convergence.json
  logs/mvcrs_stability_convergence_log.jsonl (append-only)
  Idempotent audit marker in INSTRUCTION_EXECUTION_SUMMARY.md:
    <!-- MVCRS_STABILITY_CONVERGENCE: UPDATED <UTC ISO> -->

Exit codes:
  0 success
  2 persistent write failure (fix branch created)

Gating Warning Triggers:
  potential_gating_risk = true if convergence_score < 0.45 AND ensemble_confidence > 0.7
  (early warning: instability rising despite moderate ensemble confidence)
"""
from __future__ import annotations
import json, os, sys, time, subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

# ---- Path helper ----
def _p(rel: str) -> Path:
    base = os.environ.get("MVCRS_BASE_DIR")
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent.parent / rel

# ---- Safe loaders ----
def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _load_jsonl_latest(path: Path) -> Dict[str, Any]:
    """Load latest entry from jsonl file."""
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                return json.loads(lines[-1])
    except Exception:
        pass
    return {}

# ---- Atomic writes ----
def atomic_write_json(path: Path, obj: Dict[str, Any]) -> bool:
    """Write JSON with atomic staged temp + retry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for delay in [1, 3, 9]:
        try:
            tmp = path.with_suffix('.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(obj, f, indent=2)
            tmp.replace(path)
            return True
        except Exception as e:
            print(f"⚠ write retry ({delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    print(f"✗ persistent write failure: {path}", file=sys.stderr)
    return False

def append_log(path: Path, obj: Dict[str, Any]) -> bool:
    """Append JSON line to log with retry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for delay in [1, 3, 9]:
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(obj, sort_keys=True) + "\n")
            return True
        except Exception as e:
            print(f"⚠ log retry ({delay}s): {e}", file=sys.stderr)
            time.sleep(delay)
    print(f"✗ persistent log failure: {path}", file=sys.stderr)
    return False

# ---- Marker & fix branch ----
def update_audit_marker(status: str = 'UPDATED') -> None:
    summary = _p('INSTRUCTION_EXECUTION_SUMMARY.md')
    if not summary.exists():
        return
    prefix = '<!-- MVCRS_STABILITY_CONVERGENCE:'
    ts = datetime.now(timezone.utc).isoformat()
    new_marker = f"<!-- MVCRS_STABILITY_CONVERGENCE: {status} {ts} -->"
    try:
        content = summary.read_text(encoding='utf-8')
        lines = [ln for ln in content.split('\n') if not ln.strip().startswith(prefix)]
        lines.append(new_marker)
        tmp = summary.with_suffix('.tmp')
        tmp.write_text('\n'.join(lines), encoding='utf-8')
        tmp.replace(summary)
    except Exception as e:
        print(f"⚠ marker update error: {e}", file=sys.stderr)

def create_fix_branch() -> None:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    branch = f'fix/mvcrs-stability-convergence-{ts}'
    try:
        subprocess.run(['git', 'checkout', '-b', branch], check=False)
        print(f"✓ created fix branch: {branch}")
    except Exception as e:
        print(f"⚠ fix branch error: {e}", file=sys.stderr)

# ---- Convergence computation ----
def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def extract_convergence_signal(obj: Dict[str, Any], key_path: str, default: float = 0.0) -> float:
    """Extract nested signal safely."""
    try:
        val = obj
        for key in key_path.split('.'):
            val = val[key]
        return clamp(float(val), 0.0, 1.0)
    except (KeyError, TypeError, ValueError):
        return default

def compute_convergence_score(
    drift_sig: float,
    coherence_sig: float,
    ensemble_sig: float,
    rdgl_sig: float,
    sources_count: int
) -> float:
    """
    Weighted convergence score.
    Weights: drift 0.4, coherence 0.3, ensemble 0.2, RDGL 0.1
    Penalty: -0.2 per missing source (4 expected sources: drift, coherence, ensemble, rdgl)
    
    HOTFIX (2025-11-15): Fixed penalty logic bug — was checking < 5 but only 4 sources exist.
    Changed to < 4 to match actual source count.
    """
    weights_sum = 0.0
    weighted_sum = 0.0
    penalty = 0.0
    
    # Penalize missing sources (4 expected: drift, coherence, ensemble, rdgl)
    if sources_count < 4:
        penalty = (4 - sources_count) * 0.2
    
    # Drift (0.4)
    weights_sum += 0.4
    weighted_sum += drift_sig * 0.4
    
    # Coherence (0.3)
    weights_sum += 0.3
    weighted_sum += coherence_sig * 0.3
    
    # Ensemble (0.2)
    weights_sum += 0.2
    weighted_sum += ensemble_sig * 0.2
    
    # RDGL (0.1)
    weights_sum += 0.1
    weighted_sum += rdgl_sig * 0.1
    
    if weights_sum == 0:
        return 0.0
    
    score = weighted_sum / weights_sum
    score = max(0.2, score - penalty)  # floor at 0.2
    return round(clamp(score, 0.0, 1.0), 4)

def determine_alignment(drift_sig: float, coherence_sig: float, ensemble_sig: float) -> str:
    """
    Alignment status based on signal agreement.
    """
    signals = [drift_sig, coherence_sig, ensemble_sig]
    variance = max(signals) - min(signals) if signals else 0.0
    
    if variance < 0.15:
        return "aligned"
    elif variance < 0.35:
        return "mixed"
    else:
        return "divergent"

def run_convergence_engine() -> bool:
    """Main convergence analysis."""
    print("=" * 60)
    print("MV-CRS Stability Convergence Engine — Phase XLIV")
    print("=" * 60)
    
    # Load all input sources
    drift_state = _load_json(_p('state/mvcrs_stabilization_profile.json'))
    coherence_state = _load_json(_p('state/mvcrs_horizon_coherence.json'))
    ensemble_state = _load_json(_p('state/mvcrs_multi_horizon_ensemble_state.json'))
    rdgl_state = _load_json(_p('state/rdgl_policy_adjustments.json'))
    
    sources_present = {
        'drift': bool(drift_state),
        'coherence': bool(coherence_state),
        'ensemble': bool(ensemble_state),
        'rdgl': bool(rdgl_state)
    }
    sources_count = sum(sources_present.values())
    
    # Extract signals
    drift_sig = extract_convergence_signal(drift_state, 'final_confidence', 0.0)
    coherence_sig = extract_convergence_signal(coherence_state, 'stability_score', 0.0)
    
    # For ensemble: use mean instability or confidence metric
    ensemble_sig = 0.0
    if ensemble_state:
        if 'mean_forecast_confidence' in ensemble_state:
            ensemble_sig = extract_convergence_signal(ensemble_state, 'mean_forecast_confidence', 0.0)
        elif 'forecasts' in ensemble_state:
            forecasts = ensemble_state.get('forecasts', [])
            if forecasts:
                ensemble_sig = 1.0 - clamp(sum(f.get('instability_score', 0.0) for f in forecasts) / len(forecasts), 0.0, 1.0)
    
    rdgl_sig = extract_convergence_signal(rdgl_state, 'policy_effectiveness', 0.0)
    
    # Compute convergence score
    convergence_score = compute_convergence_score(
        drift_sig, coherence_sig, ensemble_sig, rdgl_sig, sources_count
    )
    
    # Determine alignment
    alignment_status = determine_alignment(drift_sig, coherence_sig, ensemble_sig)
    
    # Confidence adjustment based on missing sources
    confidence_adjust = 1.0
    if sources_count < 4:
        confidence_adjust = max(0.2, 1.0 - (4 - sources_count) * 0.2)
    confidence_adjust = round(confidence_adjust, 4)
    
    # Gating warning logic
    ensemble_confidence = extract_convergence_signal(ensemble_state, 'mean_forecast_confidence', 0.0)
    potential_gating_risk = (convergence_score < 0.45) and (ensemble_confidence > 0.7)
    
    # Build output
    now = datetime.now(timezone.utc).isoformat() + 'Z'
    profile = {
        'convergence_score': convergence_score,
        'alignment_status': alignment_status,
        'confidence_adjust': confidence_adjust,
        'potential_gating_risk': potential_gating_risk,
        'ensemble_confidence': round(ensemble_confidence, 4),
        'signals': {
            'drift': round(drift_sig, 4),
            'coherence': round(coherence_sig, 4),
            'ensemble': round(ensemble_sig, 4),
            'rdgl': round(rdgl_sig, 4)
        },
        'sources_present': sources_present,
        'timestamp': now
    }
    
    # Write state
    profile_path = _p('state/mvcrs_stability_convergence.json')
    if not atomic_write_json(profile_path, profile):
        update_audit_marker('FAILED')
        create_fix_branch()
        return False
    
    # Write log
    log_entry = {
        'convergence_score': convergence_score,
        'alignment_status': alignment_status,
        'potential_gating_risk': potential_gating_risk,
        'timestamp': now
    }
    append_log(_p('logs/mvcrs_stability_convergence_log.jsonl'), log_entry)
    
    # Update marker
    update_audit_marker('UPDATED')
    
    # Print summary
    risk_indicator = "[RISK]" if potential_gating_risk else "OK"
    print(f"\nConvergence: {convergence_score:.4f} | Alignment: {alignment_status} | {risk_indicator}")
    print(f"Confidence Adjust: {confidence_adjust:.4f} | Sources: {sources_count}/4")
    print(f"Ensemble Conf: {ensemble_confidence:.4f}")
    print(f"[OK] Stability convergence profile generated")
    
    return True

if __name__ == '__main__':
    success = run_convergence_engine()
    sys.exit(0 if success else 2)
