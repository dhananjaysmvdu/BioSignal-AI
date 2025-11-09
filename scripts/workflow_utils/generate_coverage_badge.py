import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import hashlib

def generate(cov_xml: Path, out_svg: Path, run_id: str | None = None, updated_at: str | None = None) -> None:
    if not cov_xml.exists():
        out_svg.parent.mkdir(parents=True, exist_ok=True)
        content = (
            """<!-- Generated from run {} at {} -->
<svg xmlns='http://www.w3.org/2000/svg' width='120' height='20'>
<title>Test coverage from Continuous Tests workflow</title>
<rect width='120' height='20' fill='#555'/>
<text x='10' y='14' fill='#fff' font-size='12'>coverage: n/a</text>
</svg>""".format(run_id or 'n/a', updated_at or 'n/a')
        )
        h = hashlib.sha256(content.encode('utf-8')).hexdigest()
        content = content.replace("</svg>", f"<!-- Integrity hash: {h} --></svg>")
        out_svg.write_text(content, encoding='utf-8')
        sig_path = out_svg.parent / 'coverage.sig'
        sig_path.write_text(f"{h} coverage.svg", encoding='utf-8')
        return
    try:
        root = ET.parse(str(cov_xml)).getroot()
        rate = root.attrib.get('line-rate') or '0'
        pct = float(rate) * 100.0
    except Exception:
        pct = 0.0
    pct_str = f"{pct:.1f}%"
    color = '#e05d44'
    if pct >= 90:
        color = '#4c1'
    elif pct >= 75:
        color = '#97CA00'
    elif pct >= 60:
        color = '#dfb317'
    elif pct >= 40:
        color = '#fe7d37'
    svg = f"""<!-- Generated from run {run_id or 'n/a'} at {updated_at or 'n/a'} -->
<svg xmlns='http://www.w3.org/2000/svg' width='150' height='20'>
<title>Test coverage from Continuous Tests workflow</title>
<linearGradient id='b' x2='0' y2='100%'><stop offset='0' stop-color='#bbb' stop-opacity='.1'/><stop offset='1' stop-opacity='.1'/></linearGradient>
<mask id='a'><rect width='150' height='20' rx='3' fill='#fff'/></mask>
<g mask='url(#a)'><rect width='80' height='20' fill='#555'/><rect x='80' width='70' height='20' fill='{color}'/><rect width='150' height='20' fill='url(#b)'/></g>
<g fill='#fff' text-anchor='middle' font-family='DejaVu Sans,Verdana,Geneva,sans-serif' font-size='11'>
<text x='40' y='15' fill='#010101' fill-opacity='.3'>coverage</text><text x='40' y='15'>coverage</text>
<text x='115' y='15' fill='#010101' fill-opacity='.3'>{pct_str}</text><text x='115' y='15'>{pct_str}</text>
</g>
</svg>"""
    h = hashlib.sha256(svg.encode('utf-8')).hexdigest()
    svg = svg.replace("</svg>", f"<!-- Integrity hash: {h} --></svg>")
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg, encoding='utf-8')
    sig_path = out_svg.parent / 'coverage.sig'
    sig_path.write_text(f"{h} coverage.svg", encoding='utf-8')


def main(argv: list[str]) -> None:
    if len(argv) < 3:
        print("Usage: generate_coverage_badge.py <coverage.xml> <out.svg> [run_id] [updated_at]")
        return
    run_id = argv[3] if len(argv) > 3 else None
    updated_at = argv[4] if len(argv) > 4 else None
    generate(Path(argv[1]), Path(argv[2]), run_id, updated_at)

if __name__ == '__main__':
    main(sys.argv)
