import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

ALERT_LOG_PATH = "logs/regime_alerts.json"


def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_atomic(path: str, data: Any):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def derive_defaults(policy_path: str, warn: float, crit: float) -> tuple[float, float]:
    try:
        with open(policy_path, "r", encoding="utf-8") as f:
            policy = json.load(f)
        gpol = policy.get("governance_policy") or policy
        warn_p = float(gpol.get("regime_warning_threshold", warn))
        crit_p = float(gpol.get("regime_critical_threshold", crit))
        return warn_p, crit_p
    except Exception:
        return warn, crit


def classify(rsi: float, warn: float, crit: float) -> str | None:
    if rsi < crit:
        return "critical"
    if rsi < warn:
        return "warning"
    return None


def build_payload(severity: str, rsi: float, history_tail, owner: str, dashboard_link: str, warn: float, crit: float) -> str:
    lines = [
        f"Regime Stability Alert: {severity.capitalize()}",
        f"RSI={rsi:.2f}% (thresholds: warning<{warn} critical<{crit})",
        f"Recent RSI values: {', '.join(f'{v:.1f}' for v in history_tail)}",
        f"Owner: {owner}",
        f"Dashboard: {dashboard_link}",
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}"
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check regime stability RSI and emit alert metadata for CI soft-fail actions")
    ap.add_argument("--current", required=True, help="Path to current regime_stability.json")
    ap.add_argument("--history", required=True, help="Path to regime_stability_history.json (or logs variant)")
    ap.add_argument("--threshold-warning", type=float, default=80.0)
    ap.add_argument("--threshold-critical", type=float, default=50.0)
    ap.add_argument("--owner", default="unknown")
    ap.add_argument("--policy", default="configs/governance_policy.json")
    ap.add_argument("--dedupe-hours", type=float, default=24.0)
    ap.add_argument("--dashboard", default="reports/regime_stability_gauge.html")
    args = ap.parse_args(argv)

    warn_default = args.threshold_warning
    crit_default = args.threshold_critical
    warn_thr, crit_thr = derive_defaults(args.policy, warn_default, crit_default)

    current = load_json(args.current, {})
    rsi = float(current.get("stability_index") or current.get("rsi") or 0.0)

    # history may be in reports or logs; attempt both
    hist = load_json(args.history, {})
    # Accept format {"rsi": [{timestamp, value}, ...]}
    hist_series = []
    if isinstance(hist, dict):
        if isinstance(hist.get("rsi"), list):
            for entry in hist["rsi"][-20:]:  # last 20
                try:
                    hist_series.append(float(entry.get("value")))
                except Exception:
                    pass
    if not hist_series:
        hist_series.append(rsi)

    sev = classify(rsi, warn_thr, crit_thr)

    alert_log = load_json(ALERT_LOG_PATH, {})
    last_issue = alert_log.get("issue_number")
    last_sev = alert_log.get("severity")
    last_time_str = alert_log.get("last_alert_time")
    dedupe_until = None
    if last_time_str:
        try:
            lt = datetime.fromisoformat(last_time_str)
            dedupe_until = lt + timedelta(hours=args.dedupe_hours)
        except Exception:
            dedupe_until = None

    now = datetime.now(timezone.utc)
    create_issue = False
    comment_issue = False
    reason = "no-alert"
    issue_title = None
    severity_label = None

    if sev is None:
        # no alert; just output status
        out = {
            "status": "ok",
            "alert": False,
            "severity": None,
            "rsi": rsi,
            "issue_number": None,
            "warning_threshold": warn_thr,
            "critical_threshold": crit_thr
        }
        print(json.dumps(out))
        return 0

    severity_label = sev
    if last_sev == sev and dedupe_until and now < dedupe_until:
        # Within dedupe window – prefer comment if issue exists
        if last_issue:
            comment_issue = True
            reason = "dedupe-window-comment"
        else:
            # Rare: same severity but no issue number; allow create
            create_issue = True
            reason = "dedupe-window-new-issue-missing-prev"
    else:
        # Outside dedupe or different severity
        if last_sev == sev and last_issue:
            # same severity but outside window → comment to append timeline
            comment_issue = True
            reason = "outside-window-comment"
        else:
            # new severity or no previous
            create_issue = True
            reason = "new-severity" if last_sev != sev else "no-prev-issue"

    # Build payload (without injecting secrets)
    history_tail = hist_series[-3:]
    dashboard_link = args.dashboard
    title = f"Regime Stability Alert: {sev.capitalize()} (RSI={rsi:.0f}%)" if sev else None
    body = build_payload(sev or "", rsi, history_tail, args.owner, dashboard_link, warn_thr, crit_thr)
    labels = ["governance", "instability"] + (["critical"] if sev == "critical" else [])

    base_payload = {
        "severity": sev,
        "rsi": rsi,
        "history_tail": history_tail,
        "owner": args.owner,
        "dashboard": dashboard_link,
        "timestamp": now.isoformat(),
        "action": "comment" if comment_issue else ("create" if create_issue else "none"),
        "reason": reason,
        "warning_threshold": warn_thr,
        "critical_threshold": crit_thr,
        "title": title,
        "body": body,
        "labels": labels,
    }

    # Update log only if we're taking an action (create or comment)
    if sev and (create_issue or comment_issue):
        alert_log.update({
            "last_alert_time": now.isoformat(),
            "severity": sev,
            # issue_number will be filled by CI step after gh action; we leave existing if commenting
        })
        if last_issue and comment_issue:
            alert_log["issue_number"] = last_issue
        save_json_atomic(ALERT_LOG_PATH, alert_log)
        base_payload["log_updated"] = True
    else:
        base_payload["log_updated"] = False

    out = {
        "status": "ok",
        "alert": True,
        **base_payload,
        "issue_number": last_issue if (comment_issue and last_issue) else None,
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
