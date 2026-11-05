import pytest
from openpyxl import load_workbook

from jmeter_reporter import config
from jmeter_reporter import convert


def build(jtl, out, **kw):
    return convert.create_excel_report(str(jtl), str(out), tz=convert.resolve_timezone('UTC'), **kw)


def cells(path, sheet):
    ws = load_workbook(path)[sheet]
    return [(c.coordinate, c.value, c.number_format) for row in ws.iter_rows() for c in row
            if c.value is not None]


def test_no_raw_data_drops_only_the_raw_sheet(sample_jtl, tmp_path):
    full, slim = tmp_path / 'full.xlsx', tmp_path / 'slim.xlsx'
    info_full = build(sample_jtl, full)
    info_slim = build(sample_jtl, slim, include_raw_data=False)
    assert info_full['sheets'] == ['Сводка', 'График времени', 'Исходные данные']
    assert info_slim['sheets'] == ['Сводка', 'График времени']
    assert info_slim['raw_data'] is False and info_full['raw_data'] is True


def test_remaining_sheets_are_identical(sample_jtl, sample_xml, tmp_path):
    std, dash = sample_xml
    full, slim = tmp_path / 'full.xlsx', tmp_path / 'slim.xlsx'
    kw = dict(standard_xml=str(std), dashboard_xml=str(dash))
    build(sample_jtl, full, **kw)
    build(sample_jtl, slim, include_raw_data=False, **kw)
    for sheet in ('Сводка', 'График времени', 'Сверка'):
        assert cells(full, sheet) == cells(slim, sheet), sheet
    assert len(load_workbook(slim)['График времени']._charts) == 1


def test_summary_numbers_match(sample_jtl, tmp_path):
    a = build(sample_jtl, tmp_path / 'a.xlsx')
    b = build(sample_jtl, tmp_path / 'b.xlsx', include_raw_data=False)
    for key in ('rows', 'errors', 'labels', 'steps', 'start', 'end', 'duration', 'timezone'):
        assert a[key] == b[key], key


def test_row_limit_no_longer_matters(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, 'EXCEL_MAX_ROWS', 3)
    f = tmp_path / 'x.jtl'
    f.write_text('timeStamp,elapsed,label,success\n' + '1,1,a,true\n' * 6, encoding='utf-8')
    assert any('обрезан' in w for w in build(f, tmp_path / 'a.xlsx')['warnings'])
    slim = build(f, tmp_path / 'b.xlsx', include_raw_data=False)
    assert not any('обрезан' in w for w in slim['warnings'])


def test_missing_success_column_still_warns(tmp_path):
    f = tmp_path / 'x.jtl'
    f.write_text('timeStamp,elapsed,label\n1,10,a\n', encoding='utf-8')
    info = build(f, tmp_path / 'o.xlsx', include_raw_data=False)
    assert any('success' in w for w in info['warnings']) and info['errors'] == 1


def test_bad_files_are_still_rejected(tmp_path):
    bad = tmp_path / 'bad.jtl'
    bad.write_text('a,b\n1,2\n', encoding='utf-8')
    with pytest.raises(convert.ReportError, match='обязательных колонок'):
        build(bad, tmp_path / 'o.xlsx', include_raw_data=False)
    empty = tmp_path / 'e.jtl'
    empty.write_text('timeStamp,elapsed,label\n', encoding='utf-8')
    with pytest.raises(convert.ReportError, match='пуст'):
        build(empty, tmp_path / 'o.xlsx', include_raw_data=False)


def test_large_file_warning_mentions_the_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, 'LARGE_FILE_ROWS', 2)
    f = tmp_path / 'x.jtl'
    f.write_text('timeStamp,elapsed,label,success\n' + '1,1,a,true\n' * 4, encoding='utf-8')
    assert any('--no-raw-data' in w for w in build(f, tmp_path / 'a.xlsx')['warnings'])
    # no raw sheet -> no memory/row-limit problem -> no warning
    assert not any('большой файл' in w
                   for w in build(f, tmp_path / 'b.xlsx', include_raw_data=False)['warnings'])


# ------------------------------------------------------------ CLI / config ----

def test_cli_flags(sample_jtl, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert convert.parse_args([str(sample_jtl), 'o.xlsx'])['raw_data'] is True
    assert convert.parse_args([str(sample_jtl), 'o.xlsx', '--no-raw-data'])['raw_data'] is False


def test_config_default_and_cli_override(sample_jtl, tmp_path, monkeypatch):
    (tmp_path / 'report.toml').write_text('[report]\ninclude_raw_data = false\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    assert convert.parse_args([str(sample_jtl), 'o.xlsx'])['raw_data'] is False
    assert convert.parse_args([str(sample_jtl), 'o.xlsx', '--raw-data'])['raw_data'] is True


def test_config_validates_the_flag(tmp_path):
    path = tmp_path / 'report.toml'
    path.write_text('[report]\ninclude_raw_data = "no"\n', encoding='utf-8')
    with pytest.raises(convert.ReportError, match='true или false'):
        config.load_config(str(path))
    path.write_text('[report]\ninclude_raw_data = true\n', encoding='utf-8')
    assert config.load_config(str(path)).include_raw_data is True


def test_main_with_no_raw_data(sample_jtl, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'o.xlsx'
    convert.main([str(sample_jtl), str(out), '--no-raw-data'])
    assert 'Исходные данные' not in capsys.readouterr().out
    assert load_workbook(out).sheetnames == ['Сводка', 'График времени']


def test_version_flag(capsys):
    from jmeter_reporter import version
    assert convert.main(['--version']) == 0
    assert version.__version__ in capsys.readouterr().out
