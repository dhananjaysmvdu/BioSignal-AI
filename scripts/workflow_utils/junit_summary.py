import os
import xml.etree.ElementTree as ET
from pathlib import Path

PATH = Path('pytest.xml')

def summarize(path: Path) -> str:
    tests = failures = errors = skipped = 0
    if path.exists():
        try:
            root = ET.parse(path).getroot()
            ts = root.find('testsuite') or root
            tests = int(ts.attrib.get('tests', 0))
            failures = int(ts.attrib.get('failures', 0))
            errors = int(ts.attrib.get('errors', 0))
            skipped = int(ts.attrib.get('skipped', 0))
        except Exception as e:
            return f"Failed to parse junit report: {e}"
    else:
        return "No junit report found."
    return f"Tests: {tests}, Failures: {failures}, Errors: {errors}, Skipped: {skipped}"

def main() -> None:
    print(summarize(PATH))

if __name__ == '__main__':
    main()
