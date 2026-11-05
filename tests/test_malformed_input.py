"""Bad input must give a clear error or a warning, never silent garbage or a traceback."""
import pytest

from jmeter_reporter import compare
from jmeter_reporter import convert
from jmeter_reporter import export
from jmeter_reporter import jtl as jtl_module
from jmeter_reporter import sla
from jmeter_reporter import stats
from jmeter_reporter.errors import ReportError
from jmeter_reporter.stats import percentile
from jmeter_reporter.timeutil import resolve_timezone

HEADER = 'timeStamp,elapsed,label,responseCode,success,bytes\n'


def write(tmp_path, body, header=HEADER, name='r.jtl', encoding='utf-8'):
    path = tmp_path / name
    path.write_bytes((header + body).encode(encoding))
    return str(path)


# ---- P0-1: JMeter rounds half UP (Math.round) -------------------------------

@pytest.mark.parametrize('values, fraction, expected', [
    ([10, 20, 30, 40, 50], 0.5, 30),          # round(2.5): JMeter 3 -> 30, banker's gave 20
    (list(range(1, 10)), 0.5, 5),             # n=9
    ([7], 0.5, 7),
    ([1, 2], 0.5, 1),
    (list(range(1, 11)), 0.9, 9),
    (list(range(1, 21)), 0.95, 19),
    ([5, 6, 7], 0.99, 7),
])
def test_percentile_matches_jmeter_math_round(values, fraction, expected):
    assert percentile(values, fraction) == expected


def jmeter_reference(values, p):
    """StatCalculator.getPercentPoint written the way the Java code does it."""
    target = int(p * len(values) + 0.5)
    acc = 0
    for v in values:
        acc += 1
        if acc >= target:
            return v
    return 0


def test_percentile_against_reference_for_many_sizes():
    for n in range(1, 120):
        values = sorted((i * 7) % 53 for i in range(n))
        for p in (0.5, 0.9, 0.95, 0.99):
            assert percentile(values, p) == jmeter_reference(values, p), (n, p)


# ---- P0-3: formula injection --------------------------------------------------

EVIL = '=HYPERLINK("http://evil","x")'
EVIL_CSV = '"' + EVIL.replace('"', '""') + '"'


def test_formula_label_is_text_in_excel(tmp_path):
    from openpyxl import load_workbook
    jtl = write(tmp_path, f'1700000000000,10,{EVIL_CSV},200,true,5\n'
                          f'1700000001000,12,{EVIL_CSV},200,true,5\n')
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(jtl, str(out), tz=resolve_timezone('UTC'))
    wb = load_workbook(out)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                assert cell.data_type != 'f', (ws.title, cell.coordinate)


def test_formula_in_raw_message_is_text(tmp_path):
    from openpyxl import load_workbook
    jtl = write(tmp_path, '1700000000000,10,A,200,true,5,"=1+1"\n',
                header=HEADER.strip() + ',responseMessage\n')
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(jtl, str(out), tz=resolve_timezone('UTC'))
    ws = load_workbook(out)['Исходные данные']
    assert all(c.data_type != 'f' for row in ws.iter_rows() for c in row)


def test_csv_exports_escape_formulas(tmp_path):
    jtl = write(tmp_path, f'1700000000000,10,{EVIL_CSV},200,true,5\n')
    run = stats.load_run(jtl)
    path = tmp_path / 's.csv'
    export.write_csv(run, str(path))
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    assert lines[1].startswith("\"'=HYPERLINK") or lines[1].startswith("'=HYPERLINK")


# ---- P0-4: truncated file ------------------------------------------------------

def test_truncated_last_line_is_skipped_with_a_warning(tmp_path):
    jtl = write(tmp_path, '1700000000000,10,A,200,true,5\n1700000001000,1')
    run = stats.load_run(jtl)
    assert run.rows == 1
    assert any('оборвана' in n for n in run.notes)


def test_truncated_line_in_the_middle_is_an_error(tmp_path):
    jtl = write(tmp_path, '1700000000000,10,A,200,true,5\n1700000001000,1\n'
                          '1700000002000,10,A,200,true,5\n')
    with pytest.raises(ReportError, match='строка 3'):
        stats.load_run(jtl)


def test_excel_report_survives_truncated_tail(tmp_path):
    jtl = write(tmp_path, '1700000000000,10,A,200,true,5\n1700000001000,1')
    info = convert.create_excel_report(jtl, str(tmp_path / 'r.xlsx'),
                                       tz=resolve_timezone('UTC'))
    assert info['rows'] == 1
    assert any('оборвана' in w for w in info['warnings'])


# ---- P0-5: non-numeric timestamp / elapsed ------------------------------------

def test_non_numeric_timestamp_is_an_error_with_hint(tmp_path):
    jtl = write(tmp_path, '2026/11/05 10:00:00.000,10,A,200,true,5\n')
    with pytest.raises(ReportError, match='timestamp_format'):
        stats.load_run(jtl)
    with pytest.raises(ReportError, match='строка 2'):
        convert.create_excel_report(jtl, str(tmp_path / 'r.xlsx'))


def test_empty_elapsed_is_an_error(tmp_path):
    jtl = write(tmp_path, '1700000000000,,A,200,true,5\n')
    with pytest.raises(ReportError, match='elapsed'):
        stats.load_run(jtl)


# ---- P0-6: no success column ---------------------------------------------------

def test_sla_error_pct_without_success_column_is_refused(tmp_path):
    jtl = write(tmp_path, '1700000000000,10,A,200\n',
                header='timeStamp,elapsed,label,responseCode\n')
    run = stats.load_run(jtl)
    cfg = sla.normalize({'error_pct': 1, 'scope': 'all'})
    with pytest.raises(ReportError, match='success'):
        sla.evaluate(run, cfg)


# ---- P0-7: encoding -------------------------------------------------------------

def test_cp1251_file_gives_a_clear_error_not_mojibake(tmp_path):
    jtl = write(tmp_path, '1700000000000,10,Главная,200,true,5\n', encoding='cp1251')
    with pytest.raises(ReportError, match='JTL_ENCODING'):
        stats.load_run(jtl)


def test_cp1251_works_when_declared(tmp_path, monkeypatch):
    jtl = write(tmp_path, '1700000000000,10,Главная,200,true,5\n', encoding='cp1251')
    monkeypatch.setattr(jtl_module, 'JTL_ENCODING', 'cp1251')
    assert 'Главная' in stats.load_run(jtl).labels


def test_utf8_bom_is_accepted(tmp_path):
    path = tmp_path / 'b.jtl'
    path.write_bytes(b'\xef\xbb\xbf' + (HEADER + '1700000000000,10,A,200,true,5\n').encode())
    assert stats.load_run(str(path)).rows == 1


def test_compare_csv_escapes_formula(tmp_path):
    a = write(tmp_path, f'1700000000000,10,{EVIL_CSV},200,true,5\n', name='a.jtl')
    b = write(tmp_path, f'1700000000000,12,{EVIL_CSV},200,true,5\n', name='b.jtl')
    cmp = compare.compare_runs(stats.load_run(a), stats.load_run(b), step_pattern=".")
    path = tmp_path / 'c.csv'
    compare.write_comparison_csv(cmp, str(path))
    assert "'=HYPERLINK" in path.read_text(encoding='utf-8-sig')


# ---- comparison noise guards ----------------------------------------------------

def _run(tmp_path, name, elapsed, n=10):
    body = ''.join(f'{1700000000000 + i * 1000},{elapsed},01. A,200,true,5\n' for i in range(n))
    return stats.load_run(write(tmp_path, body, name=name))


def test_tiny_absolute_change_is_not_a_regression(tmp_path):
    base, new = _run(tmp_path, 'a.jtl', 2), _run(tmp_path, 'b.jtl', 3)   # +50%, but 1 ms
    assert not compare.compare_runs(base, new).has_regressions
    strict = compare.compare_runs(base, new, min_abs_ms=0)
    assert strict.has_regressions


def test_zero_baseline_needs_an_absolute_change(tmp_path):
    base, new = _run(tmp_path, 'a.jtl', 0), _run(tmp_path, 'b.jtl', 4)
    assert not compare.compare_runs(base, new).has_regressions
    new = _run(tmp_path, 'c.jtl', 400)
    assert compare.compare_runs(base, new).has_regressions


def test_few_samples_are_not_flagged(tmp_path):
    base, new = _run(tmp_path, 'a.jtl', 100, n=2), _run(tmp_path, 'b.jtl', 900, n=2)
    row = compare.compare_runs(base, new, step_pattern='^01').rows[0]
    assert row['status'] == 'same' and row['low_samples']


def test_html_uses_exact_error_count(tmp_path):
    body = ''.join(f'{1700000000000 + i},10,A,200,{"false" if i < 3 else "true"},5\n'
                   for i in range(7))
    run = stats.load_run(write(tmp_path, body))
    page = export.render_html(run)
    assert run.errors == 3 and '>3<' in page.replace(' ', '')


# ---- exit codes of cli.py: input problems are 2, never a Python traceback or 1 ---------------

def test_cli_missing_file_is_exit_2(tmp_path, capsys):
    from jmeter_reporter import cli
    assert cli.main(['export', str(tmp_path / 'no.jtl'), '--format', 'csv']) == 2
    assert 'не найден' in capsys.readouterr().err


def test_cli_directory_instead_of_file_is_exit_2(tmp_path):
    from jmeter_reporter import cli
    assert cli.main(['export', str(tmp_path), '--format', 'csv']) == 2


def test_cli_csv_error_is_exit_2(tmp_path, monkeypatch):
    import csv

    from jmeter_reporter import cli
    path = write(tmp_path, '1700000000000,10,A,200,true,5\n')

    class Broken:
        def __init__(self, *a, **k):
            raise csv.Error('line contains NUL')

    monkeypatch.setattr(csv, 'DictReader', Broken)
    assert cli.main(['export', path, '--format', 'csv']) == 2


def test_field_bigger_than_128_kb_is_read(tmp_path):
    body = '1700000000000,10,A,200,' + 'x' * 300_000 + ',true,5\n'
    path = write(tmp_path, body, header='timeStamp,elapsed,label,responseCode,responseMessage,'
                                        'success,bytes\n')
    assert stats.load_run(path).rows == 1


def test_unexpected_exception_is_exit_3_not_1(tmp_path, sample_jtl, monkeypatch, capsys):
    from jmeter_reporter import cli
    cfg = tmp_path / 'r.toml'
    cfg.write_text('[sla]\np90_ms = 100000\n', encoding='utf-8')

    def boom(*a, **k):
        raise RuntimeError('boom')

    monkeypatch.setattr(stats, 'load_run', boom)
    assert cli.main(['check', str(sample_jtl), '--config', str(cfg)]) == 3
    err = capsys.readouterr().err
    assert 'RuntimeError' in err and 'код выхода 3' in err


def test_convert_unexpected_exception_is_exit_3(sample_jtl, tmp_path, monkeypatch):
    monkeypatch.setattr(stats, 'load_run', lambda *a, **k: 1 / 0)
    assert convert.main([str(sample_jtl), str(tmp_path / 'o.xlsx')]) == 3


def test_help_documents_exit_codes(capsys):
    from jmeter_reporter import cli
    with pytest.raises(SystemExit):
        cli.main(['--help'])
    out = capsys.readouterr().out
    assert 'Коды выхода' in out and '3 -' in out
    convert.main(['--help'])
    assert '3 - внутренняя' in capsys.readouterr().out


def test_cli_unwritable_output_is_exit_2(tmp_path, sample_jtl):
    from jmeter_reporter import cli
    out = tmp_path / 'no' / 'such' / 'dir' / 'c.csv'
    assert cli.main(['export', str(sample_jtl), '--format', 'csv', '-o', str(out)]) == 2


def test_failed_build_keeps_the_previous_report(tmp_path, sample_jtl):
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(str(sample_jtl), str(out))
    before = out.read_bytes()
    bad = write(tmp_path, '2026/11/05,10,A,200,true,5\n', name='bad.jtl')
    with pytest.raises(ReportError):
        convert.create_excel_report(bad, str(out))
    assert out.read_bytes() == before
    assert not [p for p in tmp_path.iterdir() if p.suffix == '.tmp']


def test_history_archive_happens_only_after_a_successful_build(tmp_path, sample_jtl):
    from jmeter_reporter import history
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(str(sample_jtl), str(out))
    bad = write(tmp_path, '2026/11/05,10,A,200,true,5\n', name='bad.jtl')
    with pytest.raises(ReportError):
        convert.create_excel_report(bad, str(out), archive=lambda: history.archive_existing(out))
    assert out.exists() and not (tmp_path / 'history').exists()
    info = convert.create_excel_report(str(sample_jtl), str(out),
                                       archive=lambda: history.archive_existing(out))
    assert len(info['archived']) == 1 and out.exists()


def test_old_convert_names_still_work_but_warn():
    with pytest.warns(DeprecationWarning, match='removed in 2.0'):
        assert convert.to_int('7') == 7
    with pytest.warns(DeprecationWarning):
        assert convert.ReportError is ReportError


# ---- raw sheet: cut cells, incompatible openpyxl, temp files, archive order -----------------

def test_cells_over_the_excel_limit_are_cut_with_a_warning(tmp_path):
    from openpyxl import load_workbook
    body = '1700000000000,10,A,200,' + 'y' * 40_000 + ',true,5\n'
    path = write(tmp_path, body, header='timeStamp,elapsed,label,responseCode,responseMessage,'
                                        'success,bytes\n')
    out = tmp_path / 'r.xlsx'
    info = convert.create_excel_report(path, str(out), tz=resolve_timezone('UTC'))
    assert any('обрезано' in w and '32767' in w for w in info['warnings'])
    cell = load_workbook(out)['Исходные данные']['E2'].value
    assert len(cell) == 32767


def test_incompatible_openpyxl_output_is_a_clear_error(tmp_path, sample_jtl, monkeypatch):
    from jmeter_reporter import rawsheet
    import re
    import types
    stub = types.SimpleNamespace(search=lambda *a, **k: None, sub=re.sub, S=re.S)
    monkeypatch.setattr(rawsheet, 're', stub)  # only inside rawsheet, not the global module
    with pytest.raises(ReportError, match='Несовместимая версия openpyxl'):
        convert.create_excel_report(str(sample_jtl), str(tmp_path / 'r.xlsx'))
    assert not [p for p in tmp_path.iterdir() if p.suffix == '.tmp']


def test_temp_files_are_unique_and_have_normal_permissions(tmp_path):
    out = str(tmp_path / 'r.xlsx')
    a, b = convert._temp_path(out), convert._temp_path(out)
    assert a != b and a.endswith('.tmp')
    import os
    import stat
    assert stat.S_IMODE(os.stat(a).st_mode) == 0o666 & ~convert._UMASK


def test_report_file_has_normal_permissions(tmp_path, sample_jtl):
    import os
    import stat
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(str(sample_jtl), str(out))
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o666 & ~convert._UMASK


def test_archive_copies_the_report_so_its_path_is_never_empty(tmp_path, sample_jtl):
    from jmeter_reporter import history
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(str(sample_jtl), str(out))
    seen = {}

    def archive():
        moved = history.archive_existing(out, copy_output=True)
        seen['still_there'] = out.exists()
        return moved

    info = convert.create_excel_report(str(sample_jtl), str(out), archive=archive)
    assert seen['still_there'] and info['archived'] and out.exists()
