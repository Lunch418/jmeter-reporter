"""Release hygiene: version, changelog and the offline bundle stay consistent."""
import ast
import re
import zipfile
from pathlib import Path

import pytest

from jmeter_reporter import version
from tools import changelog_section, make_offline_bundle

ROOT = Path(__file__).resolve().parent.parent
LAUNCHERS = {'cli.py', 'convert.py', 'tui.py'}
APP_MODULES = sorted(str(p.relative_to(ROOT)) for p in ROOT.glob('jmeter_reporter/*.py'))


def test_version_is_semver():
    assert re.fullmatch(r'\d+\.\d+\.\d+', version.__version__)


def test_changelog_has_current_version():
    body = changelog_section.section(version.__version__)
    assert body and 'Added' in body


def test_changelog_section_missing_version():
    assert changelog_section.section('9.9.9') is None


def test_bundle_lists_every_launcher():
    root_py = {p.name for p in ROOT.glob('*.py')}
    assert root_py == LAUNCHERS, 'new root script: add it to RUNTIME_FILES and LAUNCHERS'
    assert LAUNCHERS <= set(make_offline_bundle.RUNTIME_FILES)
    for rel in make_offline_bundle.RUNTIME_FILES:
        assert (ROOT / rel).exists(), rel


def test_bundle_builds_without_network(tmp_path):
    archive = make_offline_bundle.build(out_dir=tmp_path, skip_download=True)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    import sys
    tag = f'{sys.version_info.major}{sys.version_info.minor}'
    prefix = f'jmeter-report-{version.__version__}-offline-py{tag}/'
    assert prefix + 'convert.py' in names
    assert prefix + 'jmeter_reporter/convert.py' in names
    assert prefix + 'INSTALL.txt' in names
    assert prefix + 'wheels/SHA256SUMS' in names


@pytest.mark.parametrize('module', APP_MODULES + sorted(LAUNCHERS))
def test_runtime_modules_do_not_use_network(module):
    tree = ast.parse((ROOT / module).read_text(encoding='utf-8'))
    banned = {'socket', 'urllib', 'http', 'requests', 'ftplib', 'smtplib', 'ssl', 'telnetlib'}
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert name.split('.')[0] not in banned, f'{module} imports {name}'


CHANGES = """# Changelog
## [Unreleased]
### Breaking
- x
## [2.0.0] - d
### Breaking
- y
## [1.2.0] - d
### Added
- z
## [1.1.0] - d
### Added
- w
"""


def test_breaking_release_needs_a_new_major_version():
    assert changelog_section.check_semver('2.0.0', CHANGES) is None
    bad = CHANGES.replace('## [1.2.0] - d\n### Added', '## [1.2.0] - d\n### Breaking')
    assert 'new major' in changelog_section.check_semver('1.2.0', bad)
    assert changelog_section.check_semver('1.1.0', CHANGES) is None
    assert 'No CHANGELOG section' in changelog_section.check_semver('9.9.9', CHANGES)


def test_released_versions_in_the_real_changelog_follow_semver():
    for released in changelog_section.versions():
        assert changelog_section.check_semver(released) is None, released


def test_bundle_always_downloads_tomli_for_python_3_10(monkeypatch, tmp_path):
    """A bundle built on 3.12 must still install on 3.10 without internet (needs tomli)."""
    calls = []
    monkeypatch.setattr(make_offline_bundle.subprocess, 'run',
                        lambda cmd, check: calls.append(cmd))
    make_offline_bundle.download('requirements.txt', tmp_path)
    extra = [cmd for cmd in calls if 'tomli>=2.0' in cmd]
    assert extra and '--platform' in extra[0] and 'any' in extra[0]  # universal wheel
    assert all('--only-binary=:all:' in cmd for cmd in calls)


def test_bundle_name_carries_the_target_python_version(tmp_path):
    archive = make_offline_bundle.build(python_version='3.10', out_dir=tmp_path,
                                        skip_download=True)
    assert archive.name.endswith('-offline-py310.zip')
