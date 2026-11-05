"""Bad input must give a clear error or a warning, never silent garbage or a traceback."""
import pytest

import compare
import convert
import export
import sla
import stats

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
    assert convert.percentile(values, fraction) == expected


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
            assert convert.percentile(values, p) == jmeter_reference(values, p), (n, p)


# ---- P0-3: formula injection --------------------------------------------------

EVIL = '=HYPERLINK("http://evil","x")'
EVIL_CSV = '"' + EVIL.replace('"', '""') + '"'


def test_formula_label_is_text_in_excel(tmp_path):
    from openpyxl import load_workbook
    jtl = write(tmp_path, f'1700000000000,10,{EVIL_CSV},200,true,5\n'
                          f'1700000001000,12,{EVIL_CSV},200,true,5\n')
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(jtl, str(out), tz=convert.resolve_timezone('UTC'))
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
    convert.create_excel_report(jtl, str(out), tz=convert.resolve_timezone('UTC'))
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
    with pytest.raises(convert.ReportError, match='строка 3'):
        stats.load_run(jtl)


def test_excel_report_survives_truncated_tail(tmp_path):
    jtl = write(tmp_path, '1700000000000,10,A,200,true,5\n1700000001000,1')
    info = convert.create_excel_report(jtl, str(tmp_path / 'r.xlsx'),
                                       tz=convert.resolve_timezone('UTC'))
    assert info['rows'] == 1
    assert any('оборвана' in w for w in info['warnings'])


# ---- P0-5: non-numeric timestamp / elapsed ------------------------------------

def test_non_numeric_timestamp_is_an_error_with_hint(tmp_path):
    jtl = write(tmp_path, '2026/11/05 10:00:00.000,10,A,200,true,5\n')
    with pytest.raises(convert.ReportError, match='timestamp_format'):
        stats.load_run(jtl)
    with pytest.raises(convert.ReportError, match='строка 2'):
        convert.create_excel_report(jtl, str(tmp_path / 'r.xlsx'))


def test_empty_elapsed_is_an_error(tmp_path):
    jtl = write(tmp_path, '1700000000000,,A,200,true,5\n')
    with pytest.raises(convert.ReportError, match='elapsed'):
        stats.load_run(jtl)


# ---- P0-6: no success column ---------------------------------------------------

def test_sla_error_pct_without_success_column_is_refused(tmp_path):
    jtl = write(tmp_path, '1700000000000,10,A,200\n',
                header='timeStamp,elapsed,label,responseCode\n')
    run = stats.load_run(jtl)
    cfg = sla.normalize({'error_pct': 1, 'scope': 'all'})
    with pytest.raises(convert.ReportError, match='success'):
        sla.evaluate(run, cfg)


# ---- P0-7: encoding -------------------------------------------------------------

def test_cp1251_file_gives_a_clear_error_not_mojibake(tmp_path):
    jtl = write(tmp_path, '1700000000000,10,Главная,200,true,5\n', encoding='cp1251')
    with pytest.raises(convert.ReportError, match='JTL_ENCODING'):
        stats.load_run(jtl)


def test_cp1251_works_when_declared(tmp_path, monkeypatch):
    jtl = write(tmp_path, '1700000000000,10,Главная,200,true,5\n', encoding='cp1251')
    monkeypatch.setattr(convert, 'JTL_ENCODING', 'cp1251')
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
