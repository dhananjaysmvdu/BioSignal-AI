"""
Governance Archetype Classifier
Identifies recurring governance states as named archetypes with supporting evidence and confidence.
Always exits 0 (non-breaking) with graceful fallbacks.
"""
from __future__ import annotations
import os
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple


def load_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def parse_days(freq: str | int | float | None) -> float | None:
    """Parse audit frequency strings like '7d' or numeric days into float days."""
    if freq is None:
        return None
    if isinstance(freq, (int, float)):
        return float(freq)
    s = str(freq).strip().lower()
    try:
        if s.endswith('d'):
            return float(s[:-1])
        if s.endswith('day') or s.endswith('days'):
            nums = ''.join(ch for ch in s if ch.isdigit() or ch == '.')
            return float(nums) if nums else None
        # ISO8601-ish PnD
        if s.startswith('p') and s.endswith('d'):
            return float(s[1:-1])
        # fallback: try float directly
        return float(s)
    except Exception:
        return None


def safe_mean_variance_from_memory(mem: Dict[str, Any], key_mean: str, key_var: str) -> Tuple[float, float]:
    m = mem.get('metrics', {}) if isinstance(mem, dict) else {}
    mean = float(m.get(key_mean, 0.0) or 0.0)
    var = float(m.get(key_var, 0.0) or 0.0)
    return mean, var


def compute_confidence(satisfied: int, total: int, cycles: int) -> int:
    if total <= 0:
        return 0
    base = int(round(100.0 * satisfied / total))
    if cycles < 5:
        base = min(base, 60)
    return base


def main():
    try:
        # Load inputs
        memory = load_json('reports/governance_memory.json') or {}
        equilibrium = load_json('reports/governance_equilibrium.json') or {}
        health = load_json('reports/governance_health.json') or {}
        stability = load_json('reports/meta_stability.json') or {}
        coherence = load_json('reports/governance_coherence.json') or {}
        policy = load_json('configs/governance_policy.json') or {}
        dtrace = load_json('logs/decision_trace.json') or {}

        cycles = int(memory.get('cycles_analyzed', 0) or 0)
        trends = memory.get('trends', {}) if isinstance(memory, dict) else {}
        ghs_trend = trends.get('ghs', 'insufficient_data')
        msi_trend = trends.get('msi', 'insufficient_data')
        overall_trend = trends.get('overall', 'stable')

        avg_coherence, _ = safe_mean_variance_from_memory(memory, 'avg_coherence', 'var_coherence')
        avg_health, _ = safe_mean_variance_from_memory(memory, 'avg_health', 'var_health')
        avg_stability, var_stability = safe_mean_variance_from_memory(memory, 'avg_stability', 'var_stability')

        coherence_index = float(coherence.get('coherence_index', avg_coherence or 100.0) or 100.0)
        coherence_status = str(coherence.get('status', 'Stable') or 'Stable')

        current_ghs = float(health.get('ghs', health.get('GovernanceHealthScore', 0.0)) or 0.0)
        current_msi = float(stability.get('meta_stability_index', 0.0) or 0.0)

        trust_weight = float(policy.get('trust_weight_factor', 0.5) or 0.5)
        human_feedback_weight = float(policy.get('human_feedback_weight', 0.0) or 0.0)
        audit_freq_days = parse_days(policy.get('audit_frequency')) or 14.0

        # Stabilization mode from last decision if present
        decisions = dtrace.get('decisions', []) if isinstance(dtrace, dict) else []
        last_mode = None
        if decisions:
            for d in reversed(decisions):
                last_mode = d.get('stabilization_mode')
                if last_mode:
                    break
        if not last_mode:
            last_mode = 'monitor'

        # Define archetype rules and evaluate
        results: List[Dict[str, Any]] = []

        # 1) Trust Expansion Phase
        te_conditions = [
            ('trust_weight_high', trust_weight >= 0.6),
            ('coherence_stable', coherence_index >= 85 and coherence_status == 'Stable'),
            ('ghs_improving', ghs_trend == 'improving'),
        ]
        te_score = sum(1 for _, ok in te_conditions if ok)
        te_conf = compute_confidence(te_score, len(te_conditions), cycles)
        te_evidence = [k for k, ok in te_conditions if ok]
        results.append({'name': 'Trust Expansion Phase', 'satisfied': te_score, 'total': len(te_conditions), 'confidence': te_conf, 'evidence': te_evidence})

        # 2) Drift Correction Phase
        dc_conditions = [
            ('msi_declining', msi_trend == 'declining'),
            ('audit_freq_increased', audit_freq_days <= 7.0),
            ('stabilization_active', last_mode == 'active'),
        ]
        dc_score = sum(1 for _, ok in dc_conditions if ok)
        dc_conf = compute_confidence(dc_score, len(dc_conditions), cycles)
        dc_evidence = [k for k, ok in dc_conditions if ok]
        results.append({'name': 'Drift Correction Phase', 'satisfied': dc_score, 'total': len(dc_conditions), 'confidence': dc_conf, 'evidence': dc_evidence})

        # 3) Equilibrium Plateau
        ep_conditions = [
            ('coherence_high', coherence_index > 90),
            ('ghs_stable', ghs_trend == 'stable'),
            ('msi_stable', msi_trend == 'stable'),
        ]
        ep_score = sum(1 for _, ok in ep_conditions if ok)
        ep_conf = compute_confidence(ep_score, len(ep_conditions), cycles)
        ep_evidence = [k for k, ok in ep_conditions if ok]
        results.append({'name': 'Equilibrium Plateau', 'satisfied': ep_score, 'total': len(ep_conditions), 'confidence': ep_conf, 'evidence': ep_evidence})

        # 4) Feedback Shock
        fs_conditions = [
            ('hf_weight_high', human_feedback_weight >= 0.6),
            ('coherence_drop', coherence_index < 80 or coherence_status != 'Stable'),
        ]
        fs_score = sum(1 for _, ok in fs_conditions if ok)
        fs_conf = compute_confidence(fs_score, len(fs_conditions), cycles)
        fs_evidence = [k for k, ok in fs_conditions if ok]
        results.append({'name': 'Feedback Shock', 'satisfied': fs_score, 'total': len(fs_conditions), 'confidence': fs_conf, 'evidence': fs_evidence})

        # 5) Meta-Stability Decline
        msd_conditions = [
            ('msi_variance_high', var_stability > 100.0),
            ('coherence_weak', coherence_index < 85 or coherence_status != 'Stable'),
        ]
        msd_score = sum(1 for _, ok in msd_conditions if ok)
        msd_conf = compute_confidence(msd_score, len(msd_conditions), cycles)
        msd_evidence = [k for k, ok in msd_conditions if ok]
        results.append({'name': 'Meta-Stability Decline', 'satisfied': msd_score, 'total': len(msd_conditions), 'confidence': msd_conf, 'evidence': msd_evidence})

        # Determine primary archetype
        best = max(results, key=lambda r: r['confidence']) if results else None
        # Normalize probabilities from raw confidences
        total_conf = sum(r['confidence'] for r in results) or 1
        probabilities = {r['name']: round(100.0 * r['confidence'] / total_conf, 1) for r in results}

        archetype = 'Unknown Archetype'
        confidence = 0
        evidence: List[str] = []
        if best and best['confidence'] >= 50:
            archetype = best['name']
            confidence = int(best['confidence'])
            evidence = best['evidence']

        # Build JSON output
        ts = datetime.utcnow().isoformat()
        out = {
            'timestamp': ts,
            'archetype': archetype,
            'confidence': confidence,
            'probabilities': probabilities,
            'supporting_evidence': evidence,
            'signals': {
                'trust_weight_factor': trust_weight,
                'human_feedback_weight': human_feedback_weight,
                'audit_frequency_days': audit_freq_days,
                'stabilization_mode': last_mode,
                'coherence_index': coherence_index,
                'coherence_status': coherence_status,
                'ghs_trend': ghs_trend,
                'msi_trend': msi_trend,
                'avg_health': avg_health,
                'avg_stability': avg_stability,
                'var_stability': var_stability,
                'current_ghs': current_ghs,
                'current_msi': current_msi,
                'overall_trend': overall_trend,
                'cycles_analyzed': cycles
            }
        }

        os.makedirs('reports', exist_ok=True)
        with open('reports/governance_archetype.json', 'w', encoding='utf-8') as f:
            json.dump(out, f, indent=2)

        # Update audit summary (idempotent block)
        summary_path = 'reports/audit_summary.md'
        try:
            if os.path.exists(summary_path):
                with open(summary_path, 'r', encoding='utf-8') as f:
                    md = f.read()
            else:
                md = '# Audit Summary\n\n'
            start = md.find('<!-- GOVERNANCE_ARCHETYPE:BEGIN -->')
            end = md.find('<!-- GOVERNANCE_ARCHETYPE:END -->')
            line = f"Archetype detected: {archetype} (confidence {confidence}%)."
            block = f"\n<!-- GOVERNANCE_ARCHETYPE:BEGIN -->\n{line}\n<!-- GOVERNANCE_ARCHETYPE:END -->\n"
            if start != -1 and end != -1:
                md = md[:start] + block + md[end+len('<!-- GOVERNANCE_ARCHETYPE:END -->'):]
            else:
                md += '\n' + block
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(md)
        except Exception:
            # Non-breaking
            pass

        # Print minimal output for CI consumption
        print(json.dumps({'archetype': archetype, 'confidence': confidence}, indent=2))
    except Exception:
        # Always exit 0
        print(json.dumps({'archetype': 'Unknown Archetype', 'confidence': 0}, indent=2))


if __name__ == '__main__':
    main()
