import argparse
import io
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone


REGIME_BLOCK_BEGIN = "<!-- REGIME_GAUGE:BEGIN -->"
REGIME_BLOCK_END = "<!-- REGIME_GAUGE:END -->"


def read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except Exception:
        return None


def write_atomic(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    # Preserve permissions if file exists
    try:
        shutil.copystat(path, tmp)
    except Exception:
        pass
    os.replace(tmp, path)


def load_rsi(current_path: str) -> tuple[float, str]:
    # Returns (rsi, timestamp_str)
    try:
        with open(current_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # support both schemas
        rsi = float(data.get("stability_index") or data.get("rsi") or 0.0)
        ts = data.get("timestamp")
        if not ts:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return rsi, ts
    except Exception:
        return 0.0, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def extract_governance_pulse_bounds(html: str) -> tuple[int, int] | None:
    # Find <section id="governance_pulse" ...> ... </section>
    start_tag = '<section id="governance_pulse"'
    start = html.find(start_tag)
    if start == -1:
        return None
    # find the opening tag end '>' from start
    open_end = html.find('>', start)
    if open_end == -1:
        return None
    # find the matching closing </section> after open_end
    end = html.find("</section>", open_end)
    if end == -1:
        return None
    return open_end + 1, end


def ensure_regime_block(html: str, gauge_rel_path: str, rsi: float, ts: str) -> str:
    caption = f"RSI {rsi:.0f}% — updated {ts}"
    block = (
        f"\n{REGIME_BLOCK_BEGIN}\n"
        f"<div id=\"regime-gauge-embed\" style=\"margin-top:16px;\">\n"
        f"  <h4 style=\"margin:0 0 8px 0;\">Regime Stability</h4>\n"
        f"  <div style=\"display:flex;align-items:center;gap:16px;flex-wrap:wrap;\">\n"
        f"    <iframe src=\"{gauge_rel_path}\" title=\"Regime Stability Gauge\" "
        f"            style=\"border:0;width:360px;height:360px;max-width:100%;\" loading=\"lazy\"></iframe>\n"
        f"    <div style=\"font-size:13px;color:#444;\">{caption}</div>\n"
        f"  </div>\n"
        f"</div>\n"
        f"{REGIME_BLOCK_END}\n"
    )

    # If markers exist, replace contents
    if REGIME_BLOCK_BEGIN in html and REGIME_BLOCK_END in html:
        pattern = re.compile(re.escape(REGIME_BLOCK_BEGIN) + r"[\s\S]*?" + re.escape(REGIME_BLOCK_END), re.MULTILINE)
        html = pattern.sub(block, html)
        return html

    # Else, insert inside Governance Pulse section if present
    bounds = extract_governance_pulse_bounds(html)
    if bounds:
        s, e = bounds
        before = html[:e]
        after = html[e:]
        return before + block + after

    # Else, just append at end of body if possible
    body_end = html.lower().rfind("</body>")
    if body_end != -1:
        return html[:body_end] + block + html[body_end:]

    # Fallback: prepend
    return block + html


def create_minimal_shell(gauge_rel_path: str, rsi: float, ts: str) -> str:
    caption = f"RSI {rsi:.0f}% — updated {ts}"
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Provenance Insights Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
  </style>
  </head>
  <body>
    <h1>Provenance Insights Dashboard</h1>
    <section id=\"governance_pulse\" style=\"margin-top:24px\">\n      <h2>Governance Pulse Over Time</h2>\n      <p style=\"max-width:640px;font-size:14px;color:#444\">Core health and stability signals.</p>\n    </section>
    {REGIME_BLOCK_BEGIN}
    <div id=\"regime-gauge-embed\" style=\"margin-top:16px;\">
      <h4 style=\"margin:0 0 8px 0;\">Regime Stability</h4>
      <div style=\"display:flex;align-items:center;gap:16px;flex-wrap:wrap;\">
        <iframe src=\"{gauge_rel_path}\" title=\"Regime Stability Gauge\" style=\"border:0;width:360px;height:360px;max-width:100%;\" loading=\"lazy\"></iframe>
        <div style=\"font-size:13px;color:#444;\">{caption}</div>
      </div>
    </div>
    {REGIME_BLOCK_END}
  </body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Embed regime stability gauge into provenance dashboard (idempotent)")
    p.add_argument("--dashboard", default="reports/provenance_dashboard.html")
    p.add_argument("--gauge", default="reports/regime_stability_gauge.html")
    p.add_argument("--current", default="reports/regime_stability.json")
    args = p.parse_args(argv)

    dashboard_path = args.dashboard
    gauge_path = args.gauge
    current_path = args.current

    rsi, ts = load_rsi(current_path)

    # Compute a relative path for iframe src (from dashboard directory)
    dash_dir = os.path.dirname(os.path.abspath(dashboard_path)) or os.getcwd()
    gauge_abs = os.path.abspath(gauge_path)
    try:
        gauge_rel = os.path.relpath(gauge_abs, start=dash_dir)
    except Exception:
        gauge_rel = gauge_path

    html = read_text(dashboard_path)
    if html is None:
        # create minimal shell
        content = create_minimal_shell(gauge_rel, rsi, ts)
        write_atomic(dashboard_path, content)
        print(json.dumps({"status": "created", "dashboard": dashboard_path, "rsi": rsi}))
        return 0

    new_html = ensure_regime_block(html, gauge_rel, rsi, ts)
    if new_html != html:
        write_atomic(dashboard_path, new_html)
        print(json.dumps({"status": "updated", "dashboard": dashboard_path, "rsi": rsi}))
    else:
        print(json.dumps({"status": "unchanged", "dashboard": dashboard_path, "rsi": rsi}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
