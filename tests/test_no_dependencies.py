"""The console tools must work with the Python standard library only (isolated machines)."""
import subprocess
import sys
from pathlib import Path

import pytest

import make_sample

ROOT = Path(__file__).resolve().parent.parent

# Importing these fails exactly as if the packages were not installed.
BLOCK = ('import sys\n'
         "for name in ('openpyxl', 'textual', 'rich', 'tomli', 'tomllib', 'et_xmlfile'):\n"
         '    sys.modules[name] = None\n'
         'sys.path.insert(0, %r)\n' % str(ROOT))


def run_blocked(code, cwd):
    return subprocess.run([sys.executable, '-I', '-c', BLOCK + code], cwd=str(cwd),
                          capture_output=True, text=True)


@pytest.fixture
def work(tmp_path):
    make_sample.write_jtl(tmp_path / 'a.jtl', iterations=6, seed=1)
    make_sample.write_jtl(tmp_path / 'b.jtl', iterations=6, seed=9)
    (tmp_path / 'report.toml').write_text(
        '[report]\ntimezone = "UTC"\n[sla]\np90_ms = 100000\n', encoding='utf-8')
    return tmp_path


def test_core_modules_import_without_third_party_packages(work):
    out = run_blocked('import convert, verify, stats, sla, compare, export, config, '
                      'workflow, cli, minitoml\nprint("ok")', work)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == 'ok'


def test_check_works(work):
    out = run_blocked("import cli, sys\nsys.exit(cli.main(['check', 'a.jtl']))", work)
    assert out.returncode == 0, out.stderr
    assert 'PASS: проверено' in out.stdout


def test_check_fails_with_exit_1(work):
    (work / 'report.toml').write_text('[sla]\np90_ms = 1\n', encoding='utf-8')
    out = run_blocked("import cli, sys\nsys.exit(cli.main(['check', 'a.jtl']))", work)
    assert out.returncode == 1 and 'FAIL: проверено' in out.stdout


def test_export_html_and_csv_work(work):
    out = run_blocked("import cli, sys\n"
                      "sys.exit(cli.main(['export', 'a.jtl', '--format', 'html', 'csv']))", work)
    assert out.returncode == 0, out.stderr
    assert (work / 'a_report.html').exists() and (work / 'a_report.csv').exists()


def test_compare_falls_back_to_csv(work):
    out = run_blocked("import cli, sys\nsys.exit(cli.main(['compare', 'a.jtl', 'b.jtl']))", work)
    assert out.returncode == 0, out.stderr
    assert 'сохранено как CSV' in out.stderr
    assert (work / 'b_compare.csv').exists() and not (work / 'b_compare.xlsx').exists()
    assert 'label,status' in (work / 'b_compare.csv').read_text(encoding='utf-8-sig')


def test_excel_report_explains_what_is_missing(work):
    out = run_blocked("import convert\n"
                      "try:\n    convert.create_excel_report('a.jtl', 'o.xlsx')\n"
                      "except convert.ReportError as e:\n    print(e)\n", work)
    assert out.returncode == 0, out.stderr
    assert 'openpyxl' in out.stdout and 'cli.py' in out.stdout


def test_convert_cli_reports_missing_openpyxl_cleanly(work):
    out = run_blocked("import convert, sys\nconvert.main(['a.jtl', 'o.xlsx'])", work)
    assert out.returncode != 0
    assert 'openpyxl' in out.stderr and 'Traceback' not in out.stderr


def test_config_uses_the_builtin_toml_parser(work):
    out = run_blocked("import config\nprint(config.tomllib.__name__)", work)
    assert out.stdout.strip() == 'minitoml'


def test_tui_explains_what_is_missing(work):
    out = subprocess.run([sys.executable, '-I', '-c', BLOCK +
                          "import runpy\nrunpy.run_path('tui.py', run_name='__main__')"],
                         cwd=str(ROOT), capture_output=True, text=True)
    assert out.returncode != 0
    assert 'textual' in out.stderr and 'Traceback' not in out.stderr
