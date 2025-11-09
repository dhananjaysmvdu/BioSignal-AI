#!/usr/bin/env python3
"""
Human-in-the-Loop Oversight Gateway
- Reads logs/decision_trace.json and reports/compliance_rationale.md
- Builds a review packet in reports/review_request.md
- If GITHUB_TOKEN available, opens a GitHub Issue with the packet body; else writes under reports/reviews/pending/
- Marks last decision entry as human_review_requested=true in logs/decision_trace.json
- Emits minimal outputs when GITHUB_OUTPUT is provided (decision_id, risk, confidence)
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOGS_PATH = os.path.join(ROOT, "logs", "decision_trace.json")
RATIONALE_MD = os.path.join(ROOT, "reports", "compliance_rationale.md")
REVIEW_MD = os.path.join(ROOT, "reports", "review_request.md")
PENDING_DIR = os.path.join(ROOT, "reports", "reviews", "pending")
POLICY_JSON = os.path.join(ROOT, "configs", "governance_policy.json")


def _read_decisions():
    if not os.path.exists(LOGS_PATH):
        return []
    try:
        with open(LOGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _write_decisions(items):
    os.makedirs(os.path.dirname(LOGS_PATH), exist_ok=True)
    with open(LOGS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def _read_file(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _risk_level(drift_prob: float, audit_depth: str) -> str:
    # simple heuristic
    if drift_prob > 0.5 or audit_depth == "full":
        return "high"
    if drift_prob > 0.2 or audit_depth == "moderate":
        return "medium"
    return "low"


def main() -> int:
    decisions = _read_decisions()
    rationale = _read_file(RATIONALE_MD)
    policy = {}
    if os.path.exists(POLICY_JSON):
        try:
            with open(POLICY_JSON, "r", encoding="utf-8") as f:
                policy = json.load(f)
        except Exception:
            policy = {}

    last = decisions[-1] if decisions else {}
    decision_id = last.get("timestamp") or datetime.now(timezone.utc).isoformat()
    decision = last.get("decision", "policy_update")
    inputs = last.get("inputs", {})
    drift_prob = float(inputs.get("drift_probability", 0.0) or 0.0)
    confidence = float(inputs.get("confidence", 0.0) or 0.0)
    audit_depth = str(policy.get("audit_depth", "unknown"))
    risk = _risk_level(drift_prob, audit_depth)

    # Build review packet
    os.makedirs(os.path.dirname(REVIEW_MD), exist_ok=True)
    packet = (
        "Review Request: Adaptive Governance Decision\n"
        f"Decision ID: {decision_id}\n"
        f"Summary: {decision}\n"
        f"Rationale: {rationale.strip()}\n"
        f"Confidence: {confidence:.2f}\n"
        f"Risk Level: {risk}\n"
    )
    with open(REVIEW_MD, "w", encoding="utf-8") as f:
        f.write(packet)

    # Prefer opening a GitHub Issue if possible
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    issue_url = None
    if token and repo:
        try:
            url = f"https://api.github.com/repos/{repo}/issues"
            title = f"Review Request: Adaptive Governance Decision {decision_id}"
            body = packet
            payload = json.dumps({"title": title, "body": body}).encode("utf-8")
            req = Request(url, data=payload, method="POST")
            req.add_header("Authorization", f"token {token}")
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("Content-Type", "application/json")
            with urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                issue_url = data.get("html_url")
        except (URLError, HTTPError):
            issue_url = None

    if issue_url is None:
        # Save under pending folder for manual triage
        os.makedirs(PENDING_DIR, exist_ok=True)
        fname = f"review_request_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.md"
        with open(os.path.join(PENDING_DIR, fname), "w", encoding="utf-8") as f:
            f.write(packet)

    # Update decision trace
    if decisions:
        decisions[-1]["human_review_requested"] = True
    else:
        decisions = [{
            "timestamp": decision_id,
            "decision": decision,
            "inputs": inputs,
            "rationale": "auto-generated",
            "human_review_requested": True,
        }]
    _write_decisions(decisions)

    # Emit outputs
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"decision_id={decision_id}\n")
            f.write(f"risk={risk}\n")
            f.write(f"confidence={int(round(confidence*100))}\n")
            if issue_url:
                f.write(f"issue_url={issue_url}\n")

    print(packet)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
