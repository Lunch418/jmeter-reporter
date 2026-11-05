import csv
import datetime as dt

import pytest
from openpyxl import load_workbook

import convert


# ---------------------------------------------------------- statistics ----

def test_percentile_uses_jmeter_formula_not_statistics_median():
    values = [10, 20, 30, 40]
    # JMeter: index round(4 * 0.5) - 1 = 1 -> 20 (statistics.median gave 25)
    assert convert.percentile(values, 0.50) == 20
    assert convert.percentile(values, 0.90) == 40


def test_percentile_single_value():
    assert convert.percentile([7], 0.99) == 7


def test_average_is_integer_division():
    assert convert.average([1, 2]) == 1
    assert convert.average([]) == 0


def test_to_int_tolerates_garbage():
    assert convert.to_int('12') == 12
    assert convert.to_int('') == 0
    assert convert.to_int(None, default=5) == 5
    assert convert.to_int('abc') == 0


def _row(ts, elapsed, ok='true', size='100', sent='10'):
    return {'timeStamp': str(ts), 'elapsed': str(elapsed), 'success': ok,
            'bytes': size, 'sentBytes': sent}


def test_collect_stats_basic():
    stats = convert.collect_stats([_row(0, 100), _row(1000, 300, ok='false')])
    assert stats['samples'] == 2
    assert stats['min'] == 100 and stats['max'] == 300
    assert stats['avg'] == 200
    assert stats['error_pct'] == 50
    # duration = from first start to LAST END: 1300 ms
    assert stats['throughput'] == pytest.approx(2 / 1.3)


def test_collect_stats_empty_cells_do_not_crash():
    stats = convert.collect_stats([{'timeStamp': '0', 'elapsed': '5', 'success': 'true',
                                    'bytes': '', 'sentBytes': ''}])
    assert stats['received_kb'] == 0


# ---------------------------------------------------------------- time ----

def test_resolve_timezone_variants():
    assert convert.resolve_timezone(None) is None
    assert convert.resolve_timezone('local') is None
    assert convert.resolve_timezone('+05:00').utcoffset(None) == dt.timedelta(hours=5)
    assert convert.resolve_timezone('UTC-3').utcoffset(None) == dt.timedelta(hours=-3)
    assert convert.resolve_timezone('Europe/Moscow') is not None


def test_resolve_timezone_rejects_unknown():
    with pytest.raises(convert.ReportError):
        convert.resolve_timezone('Mars/Olympus')


def test_format_timestamp_and_label():
    tz = convert.resolve_timezone('+03:00')
    assert convert.format_timestamp(1768471200000, tz) == '15.01.2026 13:00:00.000'
    assert convert.timezone_label(1768471200000, tz) == 'UTC+03:00'
    assert convert.format_timestamp('bad', tz) == 'N/A'


def test_format_duration():
    assert convert.format_duration(291430) == '4 мин 51,430 сек'
    assert convert.format_duration(3_661_000).startswith('1 ч 1 мин')


# --------------------------------------------------------------- parse ----

def test_parse_rejects_xml_jtl(tmp_path):
    f = tmp_path / 'x.jtl'
    f.write_text('<?xml version="1.0"?><testResults/>', encoding='utf-8')
    with pytest.raises(convert.ReportError, match='XML'):
        convert.parse_jtl_file(str(f))


def test_empty_jtl_is_an_error(tmp_path):
    f = tmp_path / 'empty.jtl'
    f.write_text('timeStamp,elapsed,label\n', encoding='utf-8')
    with pytest.raises(convert.ReportError, match='пуст'):
        convert.create_excel_report(str(f), str(tmp_path / 'o.xlsx'))


def test_missing_required_columns(tmp_path):
    f = tmp_path / 'bad.jtl'
    f.write_text('a,b\n1,2\n', encoding='utf-8')
    with pytest.raises(convert.ReportError, match='обязательных колонок'):
        convert.create_excel_report(str(f), str(tmp_path / 'o.xlsx'))


# --------------------------------------------------------------- excel ----

def test_report_end_to_end(sample_jtl, tmp_path):
    out = tmp_path / 'report.xlsx'
    info = convert.create_excel_report(str(sample_jtl), str(out),
                                       tz=convert.resolve_timezone('UTC'))
    assert out.exists()
    assert info['sheets'] == ['Сводка', 'График времени', 'Исходные данные']
    assert info['steps'] == 10
    assert info['errors'] >= 0
    assert info['timezone'] == 'UTC+00:00'
    assert info['start'].startswith('15.01.2026 10:00')

    wb = load_workbook(out)
    summary = wb['Сводка']
    assert summary['A1'].value.startswith('Отчет')
    labels = [summary.cell(row=r, column=1).value for r in range(8, 8 + info['labels'] + 1)]
    assert labels[-1] == 'TOTAL'
    assert '01. Home page' in labels

    graph = wb['График времени']
    assert len(graph._charts) == 1
    # all 10 steps present in the table (regression: the last step used to drop out)
    names = [graph.cell(row=r, column=1).value for r in range(4, 14)]
    assert names[0].startswith('01.') and names[-1].startswith('10.')

    raw = wb['Исходные данные']
    assert raw.max_row == info['rows'] + 1


def test_total_matches_sum_of_samples(sample_jtl, tmp_path):
    out = tmp_path / 'r.xlsx'
    info = convert.create_excel_report(str(sample_jtl), str(out))
    ws = load_workbook(out)['Сводка']
    per_label = sum(ws.cell(row=r, column=2).value for r in range(8, 8 + info['labels']))
    total = ws.cell(row=8 + info['labels'], column=2).value
    assert per_label == total == info['rows']


def test_custom_step_pattern(sample_jtl, tmp_path):
    out = tmp_path / 'r.xlsx'
    info = convert.create_excel_report(str(sample_jtl), str(out), step_pattern=r'^0[1-3]\.')
    assert info['steps'] == 3


def test_step_pattern_matching_nothing_gives_no_chart(sample_jtl, tmp_path):
    out = tmp_path / 'r.xlsx'
    info = convert.create_excel_report(str(sample_jtl), str(out), step_pattern=r'^ZZZ')
    assert info['steps'] == 0
    assert len(load_workbook(out)['График времени']._charts) == 0


def test_invalid_step_pattern(sample_jtl, tmp_path):
    with pytest.raises(convert.ReportError, match='регулярное'):
        convert.create_excel_report(str(sample_jtl), str(tmp_path / 'r.xlsx'),
                                    step_pattern='(')


def test_missing_success_column_warns(tmp_path):
    f = tmp_path / 'nosuccess.jtl'
    with open(f, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['timeStamp', 'elapsed', 'label'])
        w.writerow([1768471200000, 100, '01. Step'])
    info = convert.create_excel_report(str(f), str(tmp_path / 'o.xlsx'))
    assert any('success' in w for w in info['warnings'])


def test_unwritable_output_is_reported(sample_jtl, tmp_path):
    with pytest.raises(convert.ReportError, match='сохранить'):
        convert.create_excel_report(str(sample_jtl), str(tmp_path / 'no_dir' / 'o.xlsx'))


# ----------------------------------------------------------------- CLI ----

def test_cli_short_form(sample_jtl, tmp_path, capsys):
    out = tmp_path / 'cli.xlsx'
    convert.main([str(sample_jtl), str(out), '--tz', 'UTC'])
    assert out.exists()
    assert 'успешно создан' in capsys.readouterr().out


def test_cli_legacy_four_arg_form_with_verification(sample_jtl, tmp_path, sample_xml, capsys):
    std, dash = sample_xml
    out = tmp_path / 'legacy.xlsx'
    convert.main([str(sample_jtl), str(dash), str(std), str(out)])
    assert out.exists()
    assert 'Сверка с XML: расхождений нет' in capsys.readouterr().out


def test_cli_steps_option(sample_jtl, tmp_path):
    args = convert.parse_args(
        [str(sample_jtl), str(tmp_path / 'o.xlsx'), '--steps=^01', '--tz=UTC'])
    assert args['steps'] == '^01'
    assert args['standard'] is None and args['dashboard'] is None


def test_cli_four_arg_form_maps_xml_positions(sample_jtl, tmp_path):
    dash, std = tmp_path / 'd.xml', tmp_path / 's.xml'
    dash.write_text('x'); std.write_text('x')
    args = convert.parse_args([str(sample_jtl), str(dash), str(std), 'o.xlsx'])
    assert args['dashboard'] == str(dash) and args['standard'] == str(std)


def test_cli_xml_options(sample_jtl, tmp_path):
    std = tmp_path / 's.xml'; std.write_text('x')
    args = convert.parse_args([str(sample_jtl), 'o.xlsx', '--standard', str(std)])
    assert args['standard'] == str(std)


def test_cli_missing_xml_exits(sample_jtl, tmp_path):
    with pytest.raises(SystemExit):
        convert.parse_args([str(sample_jtl), 'o.xlsx', '--standard', str(tmp_path / 'no.xml')])


def test_cli_option_without_value_exits(sample_jtl):
    with pytest.raises(SystemExit):
        convert.parse_args([str(sample_jtl), 'o.xlsx', '--tz'])


def test_cli_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit):
        convert.parse_args([str(tmp_path / 'nope.jtl'), 'o.xlsx'])


def test_cli_wrong_arg_count_exits():
    with pytest.raises(SystemExit):
        convert.parse_args(['only-one'])


def test_cli_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        convert.parse_args(['--help'])
    assert exc.value.code == 0


# ------------------------------------------------------------ report.toml ----

def test_config_gives_defaults_for_tz_and_steps(sample_jtl, tmp_path, monkeypatch):
    (tmp_path / 'report.toml').write_text(
        '[report]\ntimezone = "+05:00"\nsteps = "^0[1-3]"\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    args = convert.parse_args([str(sample_jtl), 'o.xlsx'])
    assert args['steps'] == '^0[1-3]'
    assert args['tz'].utcoffset(None) == dt.timedelta(hours=5)


def test_cli_options_beat_config(sample_jtl, tmp_path, monkeypatch):
    (tmp_path / 'report.toml').write_text(
        '[report]\ntimezone = "+05:00"\nsteps = "^0[1-3]"\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    args = convert.parse_args([str(sample_jtl), 'o.xlsx', '--tz', 'UTC', '--steps', '^10'])
    assert args['steps'] == '^10' and args['tz'].utcoffset(None) == dt.timedelta(0)


def test_explicit_config_option(sample_jtl, tmp_path):
    cfg = tmp_path / 'my.toml'
    cfg.write_text('[report]\nsteps = "^05"\n', encoding='utf-8')
    assert convert.parse_args([str(sample_jtl), 'o.xlsx', '--config', str(cfg)])['steps'] == '^05'


def test_broken_config_stops_the_cli(sample_jtl, tmp_path):
    cfg = tmp_path / 'bad.toml'
    cfg.write_text('[report\n', encoding='utf-8')
    with pytest.raises(SystemExit):
        convert.parse_args([str(sample_jtl), 'o.xlsx', '--config', str(cfg)])


def test_default_steps_without_config(sample_jtl, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert convert.parse_args([str(sample_jtl), 'o.xlsx'])['steps'] == convert.DEFAULT_STEP_PATTERN


def test_large_file_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(convert, 'LARGE_FILE_ROWS', 3)
    f = tmp_path / 'big.jtl'
    f.write_text('timeStamp,elapsed,label,success\n' + '1,1,a,true\n' * 5, encoding='utf-8')
    info = convert.create_excel_report(str(f), str(tmp_path / 'o.xlsx'))
    assert any('большой файл' in w for w in info['warnings'])
