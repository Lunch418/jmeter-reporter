from pathlib import Path

import pytest

from jmeter_reporter import minitoml

try:
    import tomllib as real
except ImportError:
    try:
        import tomli as real
    except ImportError:
        real = None

ROOT = Path(__file__).resolve().parent.parent

DOCUMENTS = [
    'a = 1\nb = "x"\nc = true\nd = false\ne = 1.5\nf = -3\ng = 1_000\nh = 2e3\n',
    '# comment\n[t]\nk = "v" # tail\n[t.u]\nn = 2\n',
    'arr = [1, 2, 3]\nnames = ["a", \'b\']\n',
    'arr = [\n  1, # one\n  2,\n]\n',
    "lit = 'C:\\path\\x'\nesc = \"tab\\there \\\"q\\\" \\u0041\"\n",
    '[[x]]\nn = 1\n[[x]]\nn = 2\n',
    '[a]\n[[a.b]]\nn = 1\n[a.b.c]\nz = 1\n[[a.b]]\nn = 2\n',
    'a.b.c = 1\na.b.d = 2\n',
    'inline = { x = 1, y = "two" }\nempty = {}\n',
    '"quoted key" = 1\n[ "t t" ]\nk = 1\n',
    '',
    '\ufeff[a]\nk = 1\r\nj = 2\r\n',
]


@pytest.mark.skipif(real is None, reason='no reference parser')
@pytest.mark.parametrize('text', DOCUMENTS)
def test_same_result_as_the_reference_parser(text):
    assert minitoml.loads(text) == real.loads(text.lstrip('\ufeff'))


@pytest.mark.skipif(real is None, reason='no reference parser')
def test_example_config_parses_identically():
    raw = (ROOT / 'report.example.toml').read_bytes()
    assert minitoml.loads(raw.decode('utf-8')) == real.loads(raw.decode('utf-8'))


def test_load_reads_binary_files(tmp_path):
    path = tmp_path / 'x.toml'
    path.write_text('[sla]\np90_ms = 2000\n', encoding='utf-8')
    with open(path, 'rb') as f:
        assert minitoml.load(f) == {'sla': {'p90_ms': 2000}}


def test_report_example_values():
    data = minitoml.loads((ROOT / 'report.example.toml').read_text(encoding='utf-8'))
    assert data['report']['timezone'] == 'Europe/Moscow'
    assert data['report']['steps'] == r'^\d{2}\.'
    assert data['sla']['step'][0] == {'match': r'^02\.', 'p90_ms': 5000}


@pytest.mark.parametrize('text', [
    '[a\n',
    'a = \n',
    'a = "open\n',
    "a = 'open\n",
    'a = """multi"""\n',
    "a = '''multi'''\n",
    'a = 2026-01-01\n',
    'a = 0x1f\n',
    'a = nan\n',
    'a = 1\na = 2\n',
    '[t]\n[t]\n',
    'a = 1\n[a]\n',
    'a = [1 2]\n',
    'a = { x = 1 y = 2 }\n',
    'a = "bad \\q"\n',
    'a = "\\u00"\n',
    'a 1\n',
    'a = 1 2\n',
    '[[a]]\n[a]\nk = 1\n[[a.b]]\nx = 1\n[a.b]\n',
])
def test_malformed_or_unsupported_input_is_rejected(text):
    with pytest.raises(minitoml.TOMLDecodeError):
        minitoml.loads(text)


def test_error_mentions_the_line():
    with pytest.raises(minitoml.TOMLDecodeError, match='строка 3'):
        minitoml.loads('a = 1\nb = 2\nc = ???\n')


def test_config_falls_back_to_minitoml(monkeypatch, tmp_path):
    """config.py must work when neither tomllib nor tomli can be imported."""
    import subprocess
    import sys
    code = (
        "import sys\n"
        "sys.modules['tomllib'] = None\n"      # None in sys.modules makes the import fail
        "sys.modules['tomli'] = None\n"
        "from jmeter_reporter import config\n"
        "assert config.tomllib.__name__.endswith('minitoml'), config.tomllib\n"
        "cfg = config.load_config('report.example.toml')\n"
        "print(cfg.timezone, cfg.sla['defaults'])\n"
    )
    out = subprocess.run([sys.executable, '-I', '-c', 'import sys; sys.path.insert(0, %r);' % str(ROOT) + code],
                         cwd=str(ROOT), capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert 'Europe/Moscow' in out.stdout
