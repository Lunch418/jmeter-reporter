"""CHANGELOG helpers for releases.

    python tools/changelog_section.py v1.2.0           # print the notes of one version
    python tools/changelog_section.py --check v2.0.0   # SemVer rule: breaking -> new major
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(text):
    return text if text is not None else (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')


def section(version, text=None):
    text = _text(text)
    match = re.search(rf'^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)', text,
                      re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else None


def versions(text=None):
    """Released versions in the order of the file (newest first); 'Unreleased' is skipped."""
    return re.findall(r'^## \[(\d+\.\d+\.\d+)\]', _text(text), re.MULTILINE)


def check_semver(version, text=None):
    """Return an error message, or None when the release respects SemVer.

    A section with a '### Breaking' part must raise the MAJOR number over the previous release.
    """
    text = _text(text)
    body = section(version, text)
    if body is None:
        return f'No CHANGELOG section for {version}'
    listed = versions(text)
    later = listed[listed.index(version) + 1:] if version in listed else []
    if '### Breaking' in body and later:
        major, previous = int(version.split('.')[0]), int(later[0].split('.')[0])
        if major <= previous:
            return (f'{version} has breaking changes but its major number does not exceed '
                    f'{later[0]}: SemVer needs a new major version')
    return None


if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == '--check':
        problem = check_semver(args[1].lstrip('v'))
        if problem:
            sys.exit(problem)
        print('SemVer check OK')
    else:
        body = section(args[0].lstrip('v'))
        if body is None:
            sys.exit(f'No CHANGELOG section for {args[0]}')
        print(body)
