"""
Populate docs/literature_summary.md from a CSV of DOIs/URLs using CrossRef API.
CSV schema: doi_or_url,theme,notes[,dataset,method,metrics,limitation]
Usage:
  python -m scripts.populate_literature --csv docs/literature_sources.csv --out docs/literature_summary.md
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import sys

try:
    import requests  # type: ignore
except Exception:
    requests = None  # We'll handle missing dependency gracefully

CROSSREF_BASE = "https://api.crossref.org/works"


def extract_doi(s: str) -> Optional[str]:
    s = s.strip()
    # Direct DOI pattern
    m = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", s)
    if m:
        return m.group(0)
    # doi.org URL
    m = re.search(r"doi\.org/(10\.[^\s]+)", s)
    if m:
        return m.group(1)
    return None


def crossref_lookup(doi_or_url: str) -> Dict[str, str]:
    if requests is None:
        return {"error": "requests not installed"}
    doi = extract_doi(doi_or_url)
    url = f"{CROSSREF_BASE}/{doi}" if doi else f"{CROSSREF_BASE}?query={doi_or_url}&rows=1"
    r = requests.get(url, timeout=20)
    if r.status_code != 200:
        return {"error": f"HTTP {r.status_code}"}
    data = r.json()
    item = data.get("message") if doi else data.get("message", {}).get("items", [{}])[0]
    title = (item.get("title") or [""])[0]
    authors = ", ".join([
        " ".join([a.get("given", "").strip(), a.get("family", "").strip()]).strip()
        for a in item.get("author", [])
    ])
    year = None
    for k in ("issued", "published-print", "published-online"):
        if item.get(k, {}).get("date-parts"):
            year = item[k]["date-parts"][0][0]
            break
    container = item.get("container-title", [""])
    venue = container[0] if container else ""
    doi_out = item.get("DOI") or doi
    # Abstract may be HTML; keep short snippet if present
    abstract_html = item.get("abstract", "")
    abstract = re.sub("<[^<]+?>", "", abstract_html).strip() if abstract_html else ""
    if len(abstract) > 400:
        abstract = abstract[:400].rstrip() + " …"
    link = f"https://doi.org/{doi_out}" if doi_out else doi_or_url
    return {
        "title": title or "",
        "authors": authors or "",
        "year": str(year) if year else "",
        "venue": venue or "",
        "abstract": abstract or "",
        "link": link,
        "doi": doi_out or "",
    }


@dataclass
class Row:
    doi_or_url: str
    theme: str
    notes: str
    dataset: str = ""
    method: str = ""
    metrics: str = ""
    limitation: str = ""


def read_sources(csv_path: Path) -> list[Row]:
    rows: list[Row] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(Row(
                doi_or_url=r.get("doi_or_url", "").strip(),
                theme=(r.get("theme") or "").strip(),
                notes=(r.get("notes") or "").strip(),
                dataset=(r.get("dataset") or "").strip(),
                method=(r.get("method") or "").strip(),
                metrics=(r.get("metrics") or "").strip(),
                limitation=(r.get("limitation") or "").strip(),
            ))
    return rows


def append_auto_section(md_path: Path, entries: list[dict]):
    md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    section_header = "\n\n---\n## Auto-Populated Literature (CSV-driven)\n"
    table_header = (
        "| Title | Authors | Year | Venue | Dataset | Method | Key Metrics | Limitation | DOI/Link |\n"
        "|-------|---------|------|-------|---------|--------|------------|-----------|---------|\n"
    )
    lines = [section_header, table_header]
    for e in entries:
        line = f"| {e['title']} | {e['authors']} | {e['year']} | {e['venue']} | {e.get('dataset','')} | {e.get('method','')} | {e.get('metrics','')} | {e.get('limitation','')} | {e['link']} |\n"
        lines.append(line)
    md += "".join(lines)
    md_path.write_text(md, encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("docs/literature_summary.md"))
    args = p.parse_args()

    sources = read_sources(args.csv)
    entries = []
    for r in sources:
        meta = crossref_lookup(r.doi_or_url)
        if meta.get("error"):
            meta = {"title": "(lookup failed)", "authors": "", "year": "", "venue": "", "link": r.doi_or_url, "doi": ""}
        meta.update({
            "dataset": r.dataset,
            "method": r.method or r.theme,
            "metrics": r.metrics,
            "limitation": r.limitation,
        })
        entries.append(meta)
    append_auto_section(args.out, entries)
    print(f"Appended {len(entries)} entries to {args.out}")


if __name__ == "__main__":
    main()
