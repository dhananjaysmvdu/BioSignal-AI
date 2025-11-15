"""Chaos Drill Harness

Simulates fault conditions and validates adaptive forensic response safety mechanisms.

Fault injections:
1. Missing anchor file (expected anchor deliberately absent)
2. Corrupt reversible ledger JSON entry (invalid line injected)
3. Stale timestamp in safety brake state snapshot

Procedure:
 - Pre-populate response history with 8 recent responses (to approach brake threshold)
 - Inject faults
 - Execute 3 cycles:
     * Generate high-risk forecast via anomaly fabrication
     * Run forecaster script
     * Run adaptive response engine
 - Expect safety brake to engage on third high-risk cycle ( >=3 attempted high-risk forecasts )
 - Validate ledger contains hard action entries for first two cycles
 - Persist drill outputs to logs/chaos_drill_output.jsonl using atomic append

All file writes remain within project tree.
"""
from __future__ import annotations

import json
import os
import uuid
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FORENSICS_DIR = ROOT / 'forensics'
LOGS_DIR = ROOT / 'logs'
ERROR_LOG = FORENSICS_DIR / 'forensics_error_log.jsonl'
FORECAST_FILE = FORENSICS_DIR / 'forensics_anomaly_forecast.json'
RESPONSE_HISTORY = FORENSICS_DIR / 'response_history.jsonl'
REVERSIBLE_LEDGER = FORENSICS_DIR / 'reversible_actions_ledger.jsonl'
SAFETY_STATE_FILE = FORENSICS_DIR / 'safety_brake_state.json'
CHAOS_OUTPUT = LOGS_DIR / 'chaos_drill_output.jsonl'

ADAPTIVE_ENGINE = ROOT / 'scripts' / 'forensics' / 'adaptive_response_engine.py'
FORECASTER = ROOT / 'scripts' / 'forensics' / 'forensic_anomaly_forecaster.py'


def atomic_append_jsonl(path: Path, record: dict) -> None:
    """Atomically append a single JSON record to a JSONL file within project tree."""
    assert ROOT in path.resolve().parents or path.resolve() == ROOT, "Path must reside within project tree"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f'.tmp-{uuid.uuid4().hex}')
    existing = ''
    if path.exists():
        existing = path.read_text(encoding='utf-8')
    line = json.dumps(record) + '\n'
    with temp.open('w', encoding='utf-8') as f:
        f.write(existing)
        f.write(line)
    temp.replace(path)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fabricate_anomalies(counts_per_day: list[int]) -> None:
    """Create synthetic anomaly entries to yield high forecast risk.
    counts_per_day ordered oldest -> newest relative to today.
    """
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    today = datetime.now(timezone.utc).date()
    for idx, c in enumerate(counts_per_day):
        day = today - timedelta(days=len(counts_per_day) - 1 - idx)
        for i in range(c):
            rec = {
                'timestamp': datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
                'anomaly_id': f'{day.isoformat()}-{i}',
                'type': 'simulated_high_volume'
            }
            lines.append(json.dumps(rec))
    ERROR_LOG.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def prepopulate_response_history(existing_count: int) -> None:
    RESPONSE_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    lines = []
    for i in range(existing_count):
        rec = {
            'response_id': str(uuid.uuid4()),
            'timestamp': (now - timedelta(hours=1, minutes=i)).isoformat(),
            'event_type': 'ADAPTIVE_RESPONSE',
            'risk_level': 'high',
            'actions_taken': [{'action': 'trigger_self_healing'}],
            'status': 'hard_actions_executed'
        }
        lines.append(json.dumps(rec))
    RESPONSE_HISTORY.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def inject_faults() -> None:
    # Missing anchor file (ensure directory exists, file absent)
    anchors_dir = FORENSICS_DIR / 'anchors'
    anchors_dir.mkdir(parents=True, exist_ok=True)
    anchor_file = anchors_dir / 'primary_anchor.json'
    if anchor_file.exists():
        anchor_file.unlink()  # ensure missing

    # Corrupt ledger JSON entry
    REVERSIBLE_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    REVERSIBLE_LEDGER.write_text('}{invalid\n', encoding='utf-8')

    # Stale timestamp in safety state
    SAFETY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    stale_state = {
        'is_engaged': False,
        'response_count_24h': 0,
        'max_allowed': 10,
        'last_check': (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    }
    SAFETY_STATE_FILE.write_text(json.dumps(stale_state), encoding='utf-8')


@pytest.mark.timeout(60)
def test_chaos_drill_execution(tmp_path: Path):
    """Run chaos drill cycles and assert safety + ledger integrity."""
    # Ensure logs directory
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Pre-populate response history (8 prior high-risk responses within window)
    prepopulate_response_history(existing_count=8)

    # Inject faults
    inject_faults()

    # Run 3 high-risk cycles
    cycle_summaries = []
    for cycle in range(1, 4):
        # Fabricate anomalies: high counts ensure >25 average
        fabricate_anomalies([50, 60, 55, 65])

        # Run forecaster
        r_forecast = subprocess.run([
            os.sys.executable,
            str(FORECASTER)
        ], capture_output=True, text=True, cwd=str(ROOT))
        assert r_forecast.returncode == 0, f"Forecaster failed: {r_forecast.stderr}"

        # Verify forecast risk high
        forecast = json.loads(FORECAST_FILE.read_text(encoding='utf-8'))
        assert forecast.get('risk_level') == 'high', 'Forecast did not produce high risk'

        # Run adaptive response engine
        r_adapt = subprocess.run([
            os.sys.executable,
            str(ADAPTIVE_ENGINE)
        ], capture_output=True, text=True, cwd=str(ROOT))
        # adaptive engine may exit 1 if forecast missing; here forecast exists
        assert r_adapt.returncode == 0, f"Adaptive engine failed: {r_adapt.stderr}"

        # Parse latest response entry
        history_lines = [l for l in RESPONSE_HISTORY.read_text(encoding='utf-8').splitlines() if l.strip()]
        latest = json.loads(history_lines[-1])

        cycle_summary = {
            'cycle': cycle,
            'status': latest.get('event_type'),
            'actions_count': len(latest.get('actions_taken', [])),
            'safety_brake_engaged': latest.get('event_type') == 'SAFETY_BRAKE'
        }
        cycle_summaries.append(cycle_summary)
        atomic_append_jsonl(CHAOS_OUTPUT, {
            'timestamp': _utc_now_iso(),
            'phase': 'chaos_drill_cycle',
            'cycle': cycle,
            'stdout_adaptive': r_adapt.stdout.splitlines(),
            'stdout_forecast': r_forecast.stdout.splitlines(),
            'faults': ['missing_anchor_file', 'corrupt_ledger_entry', 'stale_safety_timestamp']
        })

    # Assertions
    # Expect safety brake engagement on third cycle
    assert cycle_summaries[-1]['safety_brake_engaged'], 'Safety brake not engaged after >=3 high-risk forecasts'

    # Ledger should contain hard action entries from prior cycles despite corrupt line
    ledger_lines = [l for l in REVERSIBLE_LEDGER.read_text(encoding='utf-8').splitlines() if l.strip()]
    parsed_entries = []
    for line in ledger_lines:
        try:
            parsed_entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # skip corrupt entries
    hard_actions = [e for e in parsed_entries if e.get('action') in {
        'trigger_self_healing', 'regenerate_anchors', 'run_full_verification', 'create_alert'
    }]
    assert hard_actions, 'No hard actions recorded in ledger'

    # Append final summary record
    atomic_append_jsonl(CHAOS_OUTPUT, {
        'timestamp': _utc_now_iso(),
        'phase': 'chaos_drill_summary',
        'cycles': cycle_summaries
    })
