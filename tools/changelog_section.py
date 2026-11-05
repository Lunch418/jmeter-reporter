"""Print the CHANGELOG.md section of one version (used for GitHub release notes)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def section(version, text=None):
    text = text if text is not None else (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(rf'^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)', text,
                      re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else None


if __name__ == '__main__':
    body = section(sys.argv[1].lstrip('v'))
    if body is None:
        sys.exit(f'No CHANGELOG section for {sys.argv[1]}')
    print(body)
