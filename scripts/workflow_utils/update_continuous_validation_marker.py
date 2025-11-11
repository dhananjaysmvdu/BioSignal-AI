#!/usr/bin/env python3
"""Update audit summary with continuous validation marker."""
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

def update_marker(integrity: str, reproducibility: str) -> None:
    audit_file = Path("audit_summary.md")
    if not audit_file.exists():
        print("audit_summary.md not found")
        sys.exit(1)
        
    content = audit_file.read_text(encoding="utf-8")
    
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    
    marker_begin = "<!-- CONTINUOUS_VALIDATION:BEGIN -->"
    marker_end = "<!-- CONTINUOUS_VALIDATION:END -->"
    
    new_marker = f"""{marker_begin}
Updated: {timestamp}
🔄 Continuous validation — Integrity: {integrity}%, Reproducibility: {reproducibility}. Latest nightly check completed.
{marker_end}"""
    
    if marker_begin in content:
        pattern = re.compile(re.escape(marker_begin) + r".*?" + re.escape(marker_end), re.DOTALL)
        content = pattern.sub(new_marker, content)
    else:
        content = content.rstrip() + "\n\n" + new_marker + "\n"
    
    audit_file.write_text(content, encoding="utf-8")
    print(f"Updated CONTINUOUS_VALIDATION marker: {integrity}%, {reproducibility}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: update_continuous_validation_marker.py <integrity> <reproducibility>")
        sys.exit(1)
    update_marker(sys.argv[1], sys.argv[2])
