#!/usr/bin/env python3
"""
Governance Ledger & Ethical Memory System
- Scans reports/reviews/completed/*.md for finalized human reviews
- Extracts decision_id, reviewer, verdict, notes, timestamp (UTC now if absent)
- Appends entries to logs/oversight_ledger.json
- Adds summary line under marker <!-- HUMAN_REVIEW:BEGIN --> in reports/audit_summary.md
- Archives any matching pending review items by moving from pending/ to completed/ if not already
Optional metrics (approval rate, turnaround) consumed later by the dashboard script.
"""
from __future__ import annotations
import os
import re
import json
import shutil
from datetime import datetime, timezone
from typing import List, Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REVIEWS_COMPLETED = os.path.join(ROOT, "reports", "reviews", "completed")
REVIEWS_PENDING = os.path.join(ROOT, "reports", "reviews", "pending")
LEDGER_JSON = os.path.join(ROOT, "logs", "oversight_ledger.json")
AUDIT_SUMMARY = os.path.join(ROOT, "reports", "audit_summary.md")
MARKER = "<!-- HUMAN_REVIEW:BEGIN -->"

DECISION_ID_RE = re.compile(r"Decision ID:\s*(.*)")
REVIEWER_RE = re.compile(r"Reviewer:\s*(.*)")
VERDICT_RE = re.compile(r"Verdict:\s*(approved|revised|rejected)", re.IGNORECASE)
NOTES_RE = re.compile(r"Notes:\s*(.*)")


def _list_completed_files() -> List[str]:
    if not os.path.isdir(REVIEWS_COMPLETED):
        return []
    return [os.path.join(REVIEWS_COMPLETED, f) for f in os.listdir(REVIEWS_COMPLETED) if f.endswith('.md')]


def _parse_review(path: str) -> Dict[str, Any]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return {}
    decision_id = _first_match(DECISION_ID_RE, content)
    reviewer = _first_match(REVIEWER_RE, content) or "Unknown"
    verdict = (_first_match(VERDICT_RE, content) or "unknown").lower()
    notes = _first_match(NOTES_RE, content) or ""
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "timestamp": ts,
        "decision_id": decision_id,
        "verdict": verdict,
        "reviewer": reviewer,
        "notes": notes[:500],
        "source_file": os.path.relpath(path, ROOT),
    }


def _first_match(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _load_ledger() -> List[Dict[str, Any]]:
    if not os.path.exists(LEDGER_JSON):
        return []
    try:
        with open(LEDGER_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _write_ledger(entries: List[Dict[str, Any]]):
    os.makedirs(os.path.dirname(LEDGER_JSON), exist_ok=True)
    with open(LEDGER_JSON, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2)


def _archive_pending(completed_decision_ids: List[str]):
    if not os.path.isdir(REVIEWS_PENDING):
        return
    for fname in os.listdir(REVIEWS_PENDING):
        if not fname.endswith('.md'):
            continue
        src = os.path.join(REVIEWS_PENDING, fname)
        try:
            with open(src, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            continue
        did = _first_match(DECISION_ID_RE, content)
        if did and did in completed_decision_ids:
            # move to completed archive with suffix to avoid overwrite
            base = os.path.splitext(fname)[0]
            new_name = f"{base}_archived.md"
            dst = os.path.join(REVIEWS_COMPLETED, new_name)
            os.makedirs(REVIEWS_COMPLETED, exist_ok=True)
            shutil.move(src, dst)


def _append_summary(entries: List[Dict[str, Any]]):
    if not entries:
        return
    os.makedirs(os.path.dirname(AUDIT_SUMMARY), exist_ok=True)
    summary_lines = []
    if os.path.exists(AUDIT_SUMMARY):
        with open(AUDIT_SUMMARY, 'r', encoding='utf-8') as f:
            summary_lines = f.read().splitlines()
    # remove existing marker section
    if MARKER in "\n".join(summary_lines):
        idx = [i for i, ln in enumerate(summary_lines) if MARKER in ln]
        if idx:
            summary_lines = summary_lines[:idx[0]]
    # build new block
    block = ["", MARKER, "## Human Review Outcomes", "Decision ID | Verdict | Reviewer | Notes", "---|---|---|---"]
    for e in entries[-10:]:  # last 10 for brevity
        block.append(f"{e.get('decision_id') or '-'} | {e.get('verdict')} | {e.get('reviewer')} | { (e.get('notes') or '').replace('|','/')[:60] }")
    summary_lines.extend(block)
    with open(AUDIT_SUMMARY, 'w', encoding='utf-8') as f:
        f.write("\n".join(summary_lines) + "\n")


def main() -> int:
    files = _list_completed_files()
    if not files:
        print("No completed reviews found.")
        return 0
    ledger = _load_ledger()
    before = len(ledger)
    new_entries = []
    existing_ids = {e.get('decision_id') for e in ledger if e.get('decision_id')}
    for path in files:
        entry = _parse_review(path)
        if not entry.get('decision_id') or entry['decision_id'] in existing_ids:
            continue
        ledger.append(entry)
        new_entries.append(entry)
    if new_entries:
        _write_ledger(ledger)
        _append_summary(ledger)
        _archive_pending([e['decision_id'] for e in new_entries if e.get('decision_id')])
        print(f"Recorded {len(new_entries)} new review entries (ledger size {len(ledger)}; was {before}).")
    else:
        print("No new review entries to record.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
