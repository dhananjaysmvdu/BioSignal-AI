#!/usr/bin/env python3
"""
Generate a standardized human oversight review template.
- Reads latest decision_id from logs/decision_trace.json
- Optional reviewer name/email via env REVIEWER (fallback 'TBD')
- Writes reports/reviews/pending/review_<decision_id>.md with YAML header and guided fields.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Any, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRACE_JSON = os.path.join(ROOT, "logs", "decision_trace.json")
PENDING_DIR = os.path.join(ROOT, "reports", "reviews", "pending")


def latest_decision_id() -> str:
    if not os.path.exists(TRACE_JSON):
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        with open(TRACE_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            return data[-1].get("timestamp") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_template(decision_id: str, reviewer: str):
    os.makedirs(PENDING_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    path = os.path.join(PENDING_DIR, f"review_{decision_id}.md")
    if os.path.exists(path):
        # Avoid overwriting; append a suffix
        path = os.path.join(PENDING_DIR, f"review_{decision_id}_dup.md")
    content = f"""---
type: human_review
status: pending
---
## Human Oversight Review
**Decision ID:** {decision_id}  
**Reviewer:** {reviewer}  
**Verdict:** [ ] Approved  [ ] Revised  [ ] Rejected  
**Rationale:**  
_Provide reasoning for the verdict, referencing audit metrics or forecast data._  
**Timestamp:** {ts}  

### Guidance
- Approved: Policy remains as tuned; note supporting metrics.
- Revised: Suggest threshold or depth adjustments; justify with drift/confidence.
- Rejected: Provide explicit concerns (ethical, statistical, security) and required changes.

### References (optional)
- Forecast JSON: reports/provenance_forecast.json
- Governance Policy: configs/governance_policy.json
- Latest Audit Summary: reports/audit_summary.md
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Generated template: {os.path.relpath(path, ROOT)}")
    return path


def main() -> int:
    reviewer = os.environ.get("REVIEWER", "TBD")
    did = latest_decision_id()
    p = write_template(did, reviewer)
    # Emit outputs for workflow consumption
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fo:
            fo.write(f"template_path={p}\n")
            fo.write(f"decision_id={did}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
