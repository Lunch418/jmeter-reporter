"""Release hygiene: version, changelog and the offline bundle stay consistent."""
import ast
import re
import zipfile
from pathlib import Path

import pytest

import version
from tools import changelog_section, make_offline_bundle

ROOT = Path(__file__).resolve().parent.parent
APP_MODULES = {p.name for p in ROOT.glob('*.py')}


def test_version_is_semver():
    assert re.fullmatch(r'\d+\.\d+\.\d+', version.__version__)


def test_changelog_has_current_version():
    body = changelog_section.section(version.__version__)
    assert body and 'Added' in body


def test_changelog_section_missing_version():
    assert changelog_section.section('9.9.9') is None


def test_bundle_lists_every_app_module():
    listed = set(make_offline_bundle.RUNTIME_FILES)
    missing = APP_MODULES - listed
    assert not missing, f'add to RUNTIME_FILES: {sorted(missing)}'
    for rel in make_offline_bundle.RUNTIME_FILES:
        assert (ROOT / rel).exists(), rel


def test_bundle_builds_without_network(tmp_path):
    archive = make_offline_bundle.build(out_dir=tmp_path, skip_download=True)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    prefix = f'jmeter-report-{version.__version__}-offline/'
    assert prefix + 'convert.py' in names
    assert prefix + 'INSTALL.txt' in names
    assert prefix + 'wheels/SHA256SUMS' in names


@pytest.mark.parametrize('module', sorted(APP_MODULES))
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
