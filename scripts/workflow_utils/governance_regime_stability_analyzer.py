"""
Governance Regime Stability Analyzer
Quantifies regime stability using dwell variance, transition entropy, and archetype recurrence.
Always exits 0 (non-breaking) and updates audit summary markers.
"""
import os
import json
import math
from datetime import datetime
from typing import Any, List, Tuple


def load_json(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path: str, data: Any):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def compute_runs(seq: List[str]) -> List[Tuple[str, int]]:
    if not seq:
        return []
    runs: List[Tuple[str, int]] = []
    cur = seq[0]
    length = 1
    for s in seq[1:]:
        if s == cur:
            length += 1
        else:
            runs.append((cur, length))
            cur = s
            length = 1
    runs.append((cur, length))
    return runs


def variance(values: List[float]) -> float:
    n = len(values)
    if n <= 1:
        return 0.0
    mean = sum(values) / n
    return sum((v - mean) ** 2 for v in values) / (n - 1)


def entropy_base2(prob: List[float]) -> float:
    h = 0.0
    for p in prob:
        if p > 0:
            h -= p * math.log(p, 2)
    return h


def main():
    try:
        transitions = load_json('reports/archetype_transitions.json') or {}
        history = load_json('logs/archetype_history.json') or {'entries': []}
        entries = history.get('entries', []) if isinstance(history, dict) else []
        seq = [e.get('archetype', 'Unknown Archetype') for e in entries]

        # Dwell variance from run lengths
        runs = compute_runs(seq)
        dwell_lengths = [length for _, length in runs]
        dwell_var = variance([float(x) for x in dwell_lengths]) if dwell_lengths else 0.0
        dwell_mean = (sum(dwell_lengths) / len(dwell_lengths)) if dwell_lengths else 0.0
        # Normalize by mean^2 to get CV^2-like measure, clamp to [0,1]
        denom = (dwell_mean ** 2) if dwell_mean > 0 else 1.0
        norm_dwell_var = min(1.0, dwell_var / denom)

        # Transition entropy across distinct transitions (exclude self-transitions)
        pairs = [(a, b) for a, b in zip(seq[:-1], seq[1:]) if a != b]
        if pairs:
            # Probability distribution over observed transition types
            counts = {}
            for p in pairs:
                counts[p] = counts.get(p, 0) + 1
            total = float(sum(counts.values()))
            probs = [c / total for c in counts.values()]
            h = entropy_base2(probs)
            h_max = math.log(max(2, len(counts)), 2)  # avoid div by zero; at least 1 bit scale
            norm_entropy = min(1.0, h / h_max) if h_max > 0 else 0.0
        else:
            h = 0.0
            norm_entropy = 0.0

        # Recurrence index = revisited archetypes / unique archetypes
        unique = set(seq)
        freq = {}
        for s in seq:
            freq[s] = freq.get(s, 0) + 1
        revisited = sum(1 for k, v in freq.items() if v >= 2)
        rec_index = (revisited / len(unique)) if unique else 0.0

        # Stability Index
        stability = 100.0 * (1.0 - norm_entropy) * (1.0 - norm_dwell_var)
        stability = max(0.0, min(100.0, stability))

        # Classification
        if stability >= 80.0:
            status = 'Regime stable'
        elif stability >= 50.0:
            status = 'Moderate volatility'
        else:
            status = 'Regime instability'

        # Compose output
        ts = datetime.utcnow().isoformat()
        out = {
            'timestamp': ts,
            'stability_index': round(stability, 2),
            'status': status,
            'metrics': {
                'dwell_variance': round(dwell_var, 4),
                'normalized_dwell_variance': round(norm_dwell_var, 4),
                'transition_entropy': round(h, 4),
                'normalized_entropy': round(norm_entropy, 4),
                'recurrence_index': round(rec_index, 4),
                'dwell_mean': round(dwell_mean, 4),
                'runs': len(runs),
                'sequence_length': len(seq)
            }
        }
        save_json('reports/regime_stability.json', out)

        # Update audit summary
        summary_path = 'reports/audit_summary.md'
        try:
            if os.path.exists(summary_path):
                with open(summary_path, 'r', encoding='utf-8') as f:
                    md = f.read()
            else:
                md = '# Audit Summary\n\n'
            start = md.find('<!-- REGIME_STABILITY:BEGIN -->')
            end = md.find('<!-- REGIME_STABILITY:END -->')
            line = (
                f"Regime Stability: {out['stability_index']}% — {status} "
                f"(entropy {out['metrics']['normalized_entropy']}, dwell σ² {out['metrics']['dwell_variance']}, recurrence {out['metrics']['recurrence_index']})."
            )
            block = f"\n<!-- REGIME_STABILITY:BEGIN -->\n{line}\n<!-- REGIME_STABILITY:END -->\n"
            if start != -1 and end != -1:
                md = md[:start] + block + md[end+len('<!-- REGIME_STABILITY:END -->'):]
            else:
                md += '\n' + block
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(md)
        except Exception:
            pass

        print(json.dumps(out, indent=2))
    except Exception:
        # Non-breaking
        print(json.dumps({'stability_index': 0, 'status': 'Regime instability'}, indent=2))


if __name__ == '__main__':
    main()
