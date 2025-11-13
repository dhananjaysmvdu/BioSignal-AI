"""Meta-Audit Summarizer & Public Transparency Feed (Phase XII Instruction 67)."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    ROOT/"federation"/"federation_error_log.jsonl",
    ROOT/"federation"/"federation_drift_log.jsonl",
    ROOT/"federation"/"guardrail_validation_log.jsonl",
    ROOT/"ethics"/"ethics_sync_log.jsonl",
    ROOT/"logs"/"schema_auto_repair.jsonl",
]
PUBLIC = ROOT/"public_meta_audit_feed.json"
PORTAL_FEED = ROOT/"portal"/"meta_audit_feed.json"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path):
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            events.append(json.loads(line))
        except Exception:
            continue
    return events


def main():
    all_events = []
    for src in SOURCES:
        all_events.extend(read_jsonl(src))
    # Sort by timestamp desc
    def ts(e):
        return e.get('timestamp') or ''
    all_events = sorted(all_events, key=ts, reverse=True)[:100]
    PUBLIC.write_text(json.dumps({
        'timestamp': utc_iso(),
        'count': len(all_events),
        'events': all_events
    }, indent=2), encoding='utf-8')
    PORTAL_FEED.parent.mkdir(parents=True, exist_ok=True)
    PORTAL_FEED.write_text(json.dumps(all_events, indent=2), encoding='utf-8')
    print(json.dumps({'events': len(all_events)}))


if __name__ == '__main__':
    main()
