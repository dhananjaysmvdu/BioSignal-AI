#!/usr/bin/env python3
"""
Reflex Integrity Sentinel — final safety layer

Guarantees each audit run maintains internal consistency between policy parameters,
meta-performance, and recorded reflex health. Validates self-reporting truthfulness.

Behavior:
- Always exits 0 (CI-safe)
- Writes reports/reflex_integrity.json
- Updates audit summary with REFLEX_INTEGRITY marker
- Flags "CRITICAL" in summary if integrity_score < 80
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ------------------------ IO helpers ------------------------

def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_audit_summary(audit_path: Path, line: str, timestamp: Optional[str] = None) -> None:
    if not audit_path.exists():
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text("# Audit Summary\n\n", encoding="utf-8")
    content = audit_path.read_text(encoding="utf-8")
    begin = "<!-- REFLEX_INTEGRITY:BEGIN -->"
    end = "<!-- REFLEX_INTEGRITY:END -->"
    normalized_ts = timestamp
    if normalized_ts:
        try:
            parsed = datetime.fromisoformat(normalized_ts.replace("Z", "+00:00"))
            normalized_ts = parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            normalized_ts = None
    if not normalized_ts:
        normalized_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    section = f"{begin}\nUpdated: {normalized_ts}\n{line}\n{end}"
    if begin in content and end in content:
        import re
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
        content = pattern.sub(section, content)
    else:
        content = content.rstrip() + "\n\n" + section + "\n"
    audit_path.write_text(content, encoding="utf-8")


# ------------------------ domain utils ------------------------

def parse_csv_timeline(csv_path: Path) -> List[Dict[str, Any]]:
    """Parse CSV produced by generate_reflex_health_dashboard.py
    Skips commented lines (#). Returns list of rows with proper types.
    """
    rows: List[Dict[str, Any]] = []
    if not csv_path.exists():
        return rows
    text = csv_path.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not lines:
        return rows
    reader = csv.DictReader(lines)
    for r in reader:
        try:
            rows.append({
                "timestamp": r.get("timestamp", ""),
                "rei_score": float(r.get("rei_score", "nan")),
                "mpi_score": float(r.get("mpi_score", "nan")),
                "confidence": float(r.get("confidence", "nan")),
                "rri_score": float(r.get("rri_score", "nan")),
                "health_score": float(r.get("health_score", "nan")),
                "classification": r.get("classification", "")
            })
        except Exception:
            # skip malformed row
            continue
    return rows


def is_finite(x: float) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(float(x))


def parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def normalize_rri_to_unit(rri: float) -> float:
    # Map [-50, +50] -> [0, 1]
    x = (rri + 50.0) / 100.0
    return max(0.0, min(1.0, x))


# ------------------------ checks ------------------------

def check_monotonic_time(history_rows: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    warnings: List[str] = []
    if len(history_rows) <= 1:
        return True, warnings
    prev: Optional[datetime] = None
    ok = True
    for idx, r in enumerate(history_rows):
        t = parse_iso(r.get("timestamp", ""))
        if t is None:
            warnings.append(f"Row {idx+1}: invalid or missing timestamp")
            ok = False
            continue
        if prev and not (t > prev):
            warnings.append(f"Non-monotonic audit timestamp at row {idx+1}")
            ok = False
        prev = t
    return ok, warnings


def check_data_integrity(rows: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    warnings: List[str] = []
    ok = True
    for idx, r in enumerate(rows):
        fields = {
            "health_score": (0.0, 100.0),
            "mpi_score": (0.0, 100.0),
            "rei_score": (0.0, 100.0),
            "confidence": (0.0, 1.0),
            "rri_score": (-100.0, 100.0),  # generous bounds
        }
        for key, (lo, hi) in fields.items():
            val = r.get(key)
            if not is_finite(val):
                warnings.append(f"Row {idx+1}: {key} not finite")
                ok = False
            else:
                if key in ("health_score", "mpi_score", "rei_score", "confidence") and not (lo <= val <= hi):
                    warnings.append(f"Row {idx+1}: {key} out of range {val}")
                    ok = False
                # rri_score can exceed typical but flag only if extreme
                if key == "rri_score" and not (lo <= val <= hi):
                    warnings.append(f"Row {idx+1}: rri_score suspicious {val}")
                    ok = False
    return ok, warnings


def check_parameter_coherence(policy: Dict[str, Any], rows: List[Dict[str, Any]]) -> Tuple[Optional[bool], List[str]]:
    """Return (ok_or_none, warnings). None if insufficient info.
    Rule: If learning_rate_factor > 1.0 (interpreted as an increase), the last health delta
    should not be worse than -10.0 percentage points.
    """
    lr = None
    # Try common locations
    if isinstance(policy, dict):
        if "learning_rate_factor" in policy:
            lr = policy.get("learning_rate_factor")
        elif "policy" in policy and isinstance(policy["policy"], dict):
            lr = policy["policy"].get("learning_rate_factor")
        elif "parameters" in policy and isinstance(policy["parameters"], dict):
            lr = policy["parameters"].get("learning_rate_factor")
    
    warnings: List[str] = []
    if lr is None or not is_finite(lr):
        warnings.append("Policy missing learning_rate_factor; coherence check skipped")
        return None, warnings
    
    if len(rows) < 2:
        warnings.append("Insufficient history for coherence check")
        return None, warnings
    
    prev = rows[-2]["health_score"]
    last = rows[-1]["health_score"]
    delta = last - prev
    if lr > 1.0 and delta < -10.0:
        warnings.append(f"Coherence breach: LR↑ ({lr}) but health declined {delta:.1f}pp (>10)")
        return False, warnings
    # Optional symmetry (not required): if LR<1 and health jumps >10, suspicious but warn only
    if lr < 1.0 and delta > 10.0:
        warnings.append(f"Note: LR↓ ({lr}) but health improved {delta:.1f}pp (>10)")
        return True, warnings
    return True, warnings


def check_cross_validation(rri_json: Optional[Dict[str, Any]], conf_json: Optional[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    warnings: List[str] = []
    if not rri_json or not conf_json:
        return True, warnings
    rri = rri_json.get("rri")
    conf = conf_json.get("confidence_weight")
    if not (is_finite(rri) and is_finite(conf)):
        return True, warnings
    rri_unit = normalize_rri_to_unit(float(rri))
    diff = abs(rri_unit - float(conf))
    if diff > 0.3:
        warnings.append(f"Minor mismatch: confidence weight drifted {diff:.2f} from RRI alignment")
        return False, warnings
    return True, warnings


# ------------------------ main logic ------------------------

def compute_integrity(
    policy_path: Path,
    self_audit_path: Path,
    csv_path: Path,
    reinforcement_path: Optional[Path],
    confidence_path: Optional[Path],
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    violations = 0
    warnings: List[str] = []

    # File completeness
    required_files = [policy_path, self_audit_path, csv_path]
    missing = [str(p) for p in required_files if not p.exists() or p.stat().st_size == 0]
    if missing:
        violations += 1
        warnings.append("Missing required artifacts: " + ", ".join(missing))

    policy = load_json(policy_path, default={})
    latest = load_json(self_audit_path, default={})
    rows = parse_csv_timeline(csv_path)

    # Monotonic time order
    ok_time, w_time = check_monotonic_time(rows)
    if not ok_time:
        violations += 1
    warnings.extend(w_time)

    # Data integrity
    ok_data, w_data = check_data_integrity(rows)
    if not ok_data:
        violations += 1
    warnings.extend(w_data)

    # Parameter coherence
    ok_param, w_param = check_parameter_coherence(policy, rows)
    if ok_param is False:
        violations += 1
    warnings.extend(w_param)

    # Cross validation (optional files)
    rri_json = load_json(reinforcement_path, default=None) if reinforcement_path else None
    conf_json = load_json(confidence_path, default=None) if confidence_path else None
    ok_cv, w_cv = check_cross_validation(rri_json, conf_json)
    if not ok_cv:
        # Treat as warning per spec (tolerance breach) — not critical by itself
        warnings.extend(w_cv)
    else:
        warnings.extend(w_cv)

    # Integrity score: 100 - 15*violations - 2.5*warnings_count
    score = 100.0 - 15.0 * violations - 2.5 * len(warnings)
    score = max(0.0, min(100.0, score))

    out = {
        "status": "ok",
        "integrity_score": round(score, 1),
        "violations": int(violations),
        "warnings": warnings,
        "timestamp": now,
    }

    # Prepare audit summary line
    warn_count = len(warnings)
    if out["integrity_score"] < 80.0:
        line = f"🧩 Reflex Integrity: {out['integrity_score']:.1f}% — CRITICAL: {violations} violation(s), {warn_count} warning(s)"
    elif violations == 0:
        label = "warning" if warn_count == 1 else "warnings"
        line = f"🧩 Reflex Integrity: {out['integrity_score']:.1f}% — {warn_count} minor {label} (no critical violations)"
    else:
        line = f"🧩 Reflex Integrity: {out['integrity_score']:.1f}% — {violations} critical violation(s), {warn_count} warning(s)"

    return out, line


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Reflex Integrity Sentinel")
    parser.add_argument("--policy", type=Path, default=Path("reports/governance_policy.json"))
    parser.add_argument("--self-audit", type=Path, default=Path("reports/reflex_self_audit.json"))
    parser.add_argument("--csv", type=Path, default=Path("exports/reflex_health_timeline.csv"))
    parser.add_argument("--reinforcement", type=Path, default=Path("reports/reflex_reinforcement.json"))
    parser.add_argument("--confidence", type=Path, default=Path("reports/confidence_adaptation.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/reflex_integrity.json"))
    parser.add_argument("--audit-summary", type=Path, default=Path("reports/audit_summary.md"))

    args = parser.parse_args(argv)

    try:
        result, line = compute_integrity(
            policy_path=args.policy,
            self_audit_path=args.self_audit,
            csv_path=args.csv,
            reinforcement_path=args.reinforcement,
            confidence_path=args.confidence,
        )
        write_json(args.output, result)
        update_audit_summary(args.audit_summary, line, result.get("timestamp"))
        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        # Always exit 0; still try to emit minimal output
        try:
            fallback = {
                "status": "error",
                "integrity_score": 0.0,
                "violations": 1,
                "warnings": [f"Sentinel error: {e}"],
                "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            }
            write_json(Path("reports/reflex_integrity.json"), fallback)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
