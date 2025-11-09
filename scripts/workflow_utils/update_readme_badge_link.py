import sys
from pathlib import Path
import re

def update_readme(repo: str, run_id: str, readme_path: Path) -> None:
    url = f"https://github.com/{repo}/actions/runs/{run_id}"
    block = (
        "<!-- COVERAGE_BADGE:BEGIN -->\n"
        f"[![Coverage](badges/coverage.svg)]({url})\n"
        "<!-- COVERAGE_BADGE:END -->\n"
    )
    if not readme_path.exists():
        return
    text = readme_path.read_text(encoding='utf-8')
    pattern = re.compile(r"<!-- COVERAGE_BADGE:BEGIN -->.*?<!-- COVERAGE_BADGE:END -->", re.DOTALL)
    if pattern.search(text):
        new_text = pattern.sub(block.strip(), text)
    else:
        # Append at top below title if markers missing
        new_text = block + "\n" + text
    readme_path.write_text(new_text, encoding='utf-8')


def main(argv: list[str]) -> None:
    if len(argv) < 3:
        print("Usage: update_readme_badge_link.py <owner/repo> <run_id> [readme_path]")
        return
    repo = argv[1]
    run_id = argv[2]
    readme = Path(argv[3]) if len(argv) > 3 else Path('README.md')
    update_readme(repo, run_id, readme)

if __name__ == '__main__':
    main(sys.argv)
