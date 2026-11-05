"""Build a self-contained bundle for machines without internet access.

Run it on a machine WITH internet access:

    python tools/make_offline_bundle.py                 # core only (openpyxl)
    python tools/make_offline_bundle.py --with-tui      # plus textual and its dependencies
    python tools/make_offline_bundle.py --python-version 3.9 --platform manylinux2014_x86_64

The result is dist/jmeter-report-<version>-offline.zip with the program files, the wheels,
SHA256SUMS and a short INSTALL.txt. Copy the zip into the closed contour and follow
docs/OFFLINE.md. Nothing in the program itself ever touches the network.
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from version import __version__  # noqa: E402

# Files the program needs at run time (everything else is development-only).
RUNTIME_FILES = [
    'cli.py', 'compare.py', 'config.py', 'convert.py', 'export.py', 'minitoml.py',
    'preview.py', 'sla.py', 'stats.py', 'tui.py', 'verify.py', 'version.py', 'workflow.py',
    'report.example.toml', 'requirements.txt', 'requirements-tui.txt', 'README.md',
    'CHANGELOG.md', 'docs/OFFLINE.md',
]

INSTALL_TXT = """Offline install (no internet needed)
====================================

1. Check the files:   sha256sum -c SHA256SUMS      (inside the wheels folder)
2. Create a venv:     python3 -m venv .venv && . .venv/bin/activate
3. Install:           pip install --no-index --find-links wheels -r requirements.txt
   With the TUI:      pip install --no-index --find-links wheels -r requirements-tui.txt
4. Run:               python convert.py --version

No wheels at all? These work with the Python standard library only:
   python cli.py check run.jtl
   python cli.py export run.jtl --format html
Details: docs/OFFLINE.md
"""


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def download(requirements, target, python_version=None, platform=None):
    cmd = [sys.executable, '-m', 'pip', 'download', '-r', str(ROOT / requirements),
           '-d', str(target), '--only-binary=:all:']
    if python_version:
        cmd += ['--python-version', python_version]
    if platform:
        cmd += ['--platform', platform]
    subprocess.run(cmd, check=True)


def build(with_tui=False, python_version=None, platform=None, out_dir=None, skip_download=False):
    out_dir = Path(out_dir or ROOT / 'dist')
    name = f'jmeter-report-{__version__}-offline'
    stage = out_dir / name
    if stage.exists():
        shutil.rmtree(stage)
    (stage / 'wheels').mkdir(parents=True)

    for rel in RUNTIME_FILES:
        src = ROOT / rel
        if not src.exists():
            raise SystemExit(f'Missing runtime file: {rel}')
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (stage / 'INSTALL.txt').write_text(INSTALL_TXT, encoding='utf-8')

    if not skip_download:
        download('requirements-tui.txt' if with_tui else 'requirements.txt',
                 stage / 'wheels', python_version, platform)
    sums = [f'{sha256(p)}  {p.name}' for p in sorted((stage / 'wheels').glob('*'))]
    (stage / 'wheels' / 'SHA256SUMS').write_text('\n'.join(sums) + '\n', encoding='utf-8')

    archive = out_dir / f'{name}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                zf.write(path, Path(name) / path.relative_to(stage))
    shutil.rmtree(stage)
    return archive


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--with-tui', action='store_true', help='include textual and friends')
    parser.add_argument('--python-version', help='target Python, e.g. 3.9')
    parser.add_argument('--platform', help='target pip platform tag, e.g. manylinux2014_x86_64')
    parser.add_argument('--out', help='output folder (default: dist)')
    parser.add_argument('--no-download', action='store_true', help='program files only')
    args = parser.parse_args(argv)
    archive = build(args.with_tui, args.python_version, args.platform, args.out, args.no_download)
    print(f'Bundle: {archive} ({archive.stat().st_size // 1024} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
