"""
Governance Archetype Transition Mapper
Tracks transitions between governance archetypes over time and detects regime shifts.
Always exits 0 with graceful fallbacks.
"""
import os
import json
from datetime import datetime
from collections import defaultdict, Counter
from typing import List, Dict, Any, Tuple


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
    """Compute consecutive runs (archetype, length)."""
    if not seq:
        return []
    runs = []
    current = seq[0]
    length = 1
    for s in seq[1:]:
        if s == current:
            length += 1
        else:
            runs.append((current, length))
            current = s
            length = 1
    runs.append((current, length))
    return runs


def main():
    try:
        # Load current archetype
        current = load_json('reports/governance_archetype.json') or {}
        curr_name = str(current.get('archetype', 'Unknown Archetype') or 'Unknown Archetype')
        curr_conf = int(current.get('confidence', 0) or 0)
        ts = datetime.utcnow().isoformat()

        # Load/initialize history
        hist_path = 'logs/archetype_history.json'
        history = load_json(hist_path)
        if not isinstance(history, dict) or 'entries' not in history:
            history = {'entries': []}

        # Append current entry
        entry = {'timestamp': ts, 'archetype': curr_name, 'confidence': curr_conf}
        history['entries'].append(entry)

        # Build sequences
        entries = history['entries']
        arche_seq = [e.get('archetype', 'Unknown Archetype') for e in entries]
        conf_seq = [int(e.get('confidence', 0) or 0) for e in entries]

        # Transition counts
        archetypes = sorted(set(arche_seq))
        counts: Dict[str, Dict[str, int]] = {a: {b: 0 for b in archetypes} for a in archetypes}
        for a, b in zip(arche_seq[:-1], arche_seq[1:]):
            counts[a][b] = counts[a].get(b, 0) + 1

        # Probabilities per row
        probs: Dict[str, Dict[str, float]] = {a: {} for a in archetypes}
        for a in archetypes:
            total = sum(counts[a].values())
            if total > 0:
                for b in archetypes:
                    probs[a][b] = round(100.0 * counts[a].get(b, 0) / total, 1)
            else:
                for b in archetypes:
                    probs[a][b] = 0.0

        # Most frequent transitions
        trans_counter = Counter()
        for a, b in zip(arche_seq[:-1], arche_seq[1:]):
            if a != b:
                trans_counter[(a, b)] += 1
        most_frequent = [
            {
                'from': a,
                'to': b,
                'count': c,
                'probability_pct_from_row': probs.get(a, {}).get(b, 0.0)
            }
            for (a, b), c in trans_counter.most_common(5)
        ]

        # Dwell times (average run length per archetype)
        runs = compute_runs(arche_seq)
        dwell_sum: Dict[str, int] = defaultdict(int)
        dwell_cnt: Dict[str, int] = defaultdict(int)
        for a, length in runs:
            dwell_sum[a] += length
            dwell_cnt[a] += 1
        dwell_avg = {a: (dwell_sum[a] / dwell_cnt[a]) for a in archetypes if dwell_cnt[a] > 0}

        # Recent shift detection
        latest_transition = None
        if len(entries) >= 2:
            prev = entries[-2]
            if prev.get('archetype') != curr_name and curr_conf >= 60:
                # Compute dwell for previous run length
                # Find last run length for previous archetype
                prev_run_len = 1
                i = len(arche_seq) - 2
                while i - 1 >= 0 and arche_seq[i - 1] == prev.get('archetype'):
                    prev_run_len += 1
                    i -= 1
                latest_transition = {
                    'from': prev.get('archetype'),
                    'to': curr_name,
                    'confidence': curr_conf,
                    'dwell_cycles': prev_run_len,
                    'timestamp': ts,
                    'event': True
                }
        if latest_transition is None:
            latest_transition = {
                'from': entries[-2]['archetype'] if len(entries) >= 2 else curr_name,
                'to': curr_name,
                'confidence': curr_conf,
                'dwell_cycles': runs[-1][1] if runs else 1,
                'timestamp': ts,
                'event': False
            }

        # Save history
        save_json(hist_path, history)

        # Build output
        output = {
            'timestamp': ts,
            'entries_count': len(entries),
            'latest_archetype': curr_name,
            'latest_confidence': curr_conf,
            'transition_counts': counts,
            'transition_probabilities_pct': probs,
            'most_frequent_transitions': most_frequent,
            'dwell_time_avg_cycles': dwell_avg,
            'last_transition': latest_transition
        }
        save_json('reports/archetype_transitions.json', output)

        # Update audit summary
        summary_path = 'reports/audit_summary.md'
        try:
            if os.path.exists(summary_path):
                with open(summary_path, 'r', encoding='utf-8') as f:
                    md = f.read()
            else:
                md = '# Audit Summary\n\n'
            start = md.find('<!-- ARCHETYPE_TRANSITIONS:BEGIN -->')
            end = md.find('<!-- ARCHETYPE_TRANSITIONS:END -->')
            lt = output['last_transition']
            line = (
                f"Latest transition: {lt['from']} → {lt['to']} "
                f"(confidence {lt['confidence']}%, dwell {lt['dwell_cycles']} cycles)."
            )
            block = f"\n<!-- ARCHETYPE_TRANSITIONS:BEGIN -->\n{line}\n<!-- ARCHETYPE_TRANSITIONS:END -->\n"
            if start != -1 and end != -1:
                md = md[:start] + block + md[end+len('<!-- ARCHETYPE_TRANSITIONS:END -->'):]
            else:
                md += '\n' + block
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(md)
        except Exception:
            pass

        # Print minimal CI output
        print(json.dumps({
            'latest_from': output['last_transition']['from'],
            'latest_to': output['last_transition']['to'],
            'confidence': output['last_transition']['confidence']
        }, indent=2))
    except Exception:
        # Non-breaking
        print(json.dumps({'latest_from': 'Unknown', 'latest_to': 'Unknown', 'confidence': 0}, indent=2))


if __name__ == '__main__':
    main()
