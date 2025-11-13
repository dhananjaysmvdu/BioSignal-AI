"""Federation Peer Exchange Layer (Phase XII Instruction 64).

Discovers peers, pulls status and certification policies, computes deltas,
emits a comparison report, and logs peer_exchange events.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
PEERS = ROOT/"federation"/"peers.json"
OUR_STATUS = ROOT/"federation"/"federation_status.json"
OUR_POLICY = ROOT/"config"/"certification_policy.json"
REPORT = ROOT/"results"/"federation_peer_exchange_report.json"
DRIFT_LOG = ROOT/"federation"/"federation_drift_log.jsonl"
AUDIT = ROOT/"audit_summary.md"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fetch_json(url: str) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:  # nosec - used for internal JSON pulls
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def load_peer_resource(base: str, rel: str) -> Dict[str, Any]:
    # Support: http(s)://, file://, local relative paths
    if base.startswith("http://") or base.startswith("https://"):
        return fetch_json(base.rstrip("/") + "/" + rel)
    # treat as local path
    p = (ROOT/Path(base)/rel).resolve()
    if p.exists():
        return read_json(p)
    return {}


def append_log(event: str, message: str, meta: Dict[str, Any] | None = None):
    DRIFT_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": utc_iso(), "event": event, "message": message}
    if meta:
        payload["metadata"] = meta
    with DRIFT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def main():
    peers = read_json(PEERS)
    if not isinstance(peers, list):
        peers = []
    our_status = read_json(OUR_STATUS)
    our_policy = read_json(OUR_POLICY)
    our_fii = float(our_status.get("federation_integrity_index", 98.0))
    our_drift_tol = float(our_policy.get("drift_tolerance_pct", 1.0))
    our_guard_win = float(our_policy.get("guardrail_window_min", 2))

    results: List[Dict[str, Any]] = []
    for peer in peers:
        base = str(peer.get("base", "")).strip()
        name = str(peer.get("name", base or "peer"))
        if not base:
            continue
        p_status = load_peer_resource(base, "federation/federation_status.json")
        p_policy = load_peer_resource(base, "config/certification_policy.json")
        fii = float(p_status.get("federation_integrity_index", 0.0))
        drift_tol = float(p_policy.get("drift_tolerance_pct", our_drift_tol))
        guard_win = float(p_policy.get("guardrail_window_min", our_guard_win))
        results.append({
            "peer": name,
            "base": base,
            "peer_fii": fii,
            "delta_fii": fii - our_fii,
            "peer_drift_tolerance_pct": drift_tol,
            "delta_drift_tolerance_pct": drift_tol - our_drift_tol,
            "peer_guardrail_window_min": guard_win,
            "delta_guardrail_window_min": guard_win - our_guard_win,
        })

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "timestamp": utc_iso(),
        "peers_compared": len(results),
        "our": {"fii": our_fii, "drift_tolerance_pct": our_drift_tol, "guardrail_window_min": our_guard_win},
        "peers": results,
    }
    REPORT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    append_log("peer_exchange", "Completed federation peer comparison.", {"count": len(results)})
    if AUDIT.exists():
        with AUDIT.open("a", encoding="utf-8") as fh:
            fh.write(f"<!-- FEDERATION_PEER_EXCHANGE: UPDATED {utc_iso()} -->\n")
    print(json.dumps({"peers_compared": len(results)}))


if __name__ == "__main__":
    main()
