import pytest
from openpyxl import load_workbook

from jmeter_reporter import convert
from jmeter_reporter import verify
from jmeter_reporter.errors import ReportError
from jmeter_reporter.jtl import parse_jtl_file
from jmeter_reporter.stats import stats_of_rows


def _stats(sample_jtl):
    rows = parse_jtl_file(str(sample_jtl))
    grouped = {}
    for r in rows:
        grouped.setdefault(r['label'], []).append(r)
    return [dict(stats_of_rows(v), label=k) for k, v in grouped.items()]


def test_standard_results_parsing(sample_xml):
    std, _ = sample_xml
    data = verify.parse_standard_results(std)
    assert '01. Home page' in data
    assert set(data['01. Home page']) == {'samples', 'avg', 'min', 'median', 'p90',
                                          'p95', 'max', 'error_pct'}


def test_dashboard_parsing_handles_invalid_xml(sample_xml):
    _, dash = sample_xml
    # tags like <01. Home page> are not valid XML: the parser must not use ElementTree
    data = verify.parse_dashboard(dash)
    entry = data['01. Home page']
    assert set(entry) == {'avg', 'median', 'p90', 'p95'}


def test_consistent_files_have_no_mismatches(sample_jtl, sample_xml):
    std, dash = sample_xml
    stats = _stats(sample_jtl)
    rows = (verify.compare(stats, verify.parse_standard_results(std), 'std')
            + verify.compare(stats, verify.parse_dashboard(dash), 'dash'))
    summary = verify.summarize(rows)
    assert summary['ok'] and summary['checked'] > 100


def test_mismatch_is_detected(sample_jtl, sample_xml):
    std, _ = sample_xml
    text = std.read_text(encoding='utf-8')
    std.write_text(text.replace('<average>', '<average>9', 1), encoding='utf-8')
    rows = verify.compare(_stats(sample_jtl), verify.parse_standard_results(std), 'std')
    bad = [r for r in rows if not r['ok']]
    assert len(bad) == 1 and bad[0]['metric'] == 'avg'


def test_label_with_trailing_space_matches():
    stats = [{'label': 'Section ', 'samples': 3, 'avg': 10, 'median': 9, 'p90': 12,
              'p95': 12, 'min': 1, 'max': 12, 'error_pct': 0.0}]
    rows = verify.compare(stats, {'Section': {'avg': 10, 'samples': 3}}, 'x')
    assert all(r['ok'] for r in rows)


def test_label_missing_in_jtl_is_flagged():
    rows = verify.compare([], {'Ghost': {'avg': 1}}, 'x')
    assert rows[0]['actual'] is None and not rows[0]['ok']


def test_error_percent_tolerance():
    stats = [{'label': 'A', 'error_pct': 2.5}]
    assert verify.compare(stats, {'A': {'error_pct': 2.5}}, 'x')[0]['ok']
    assert not verify.compare(stats, {'A': {'error_pct': 3.0}}, 'x')[0]['ok']


def test_broken_standard_xml(tmp_path):
    f = tmp_path / 's.xml'
    f.write_text('<results><api>', encoding='utf-8')
    with pytest.raises(ReportError, match='XML'):
        verify.parse_standard_results(f, ReportError)


def test_wrong_files_are_rejected(tmp_path):
    f = tmp_path / 'e.xml'
    f.write_text('<results></results>', encoding='utf-8')
    with pytest.raises(ReportError):
        verify.parse_standard_results(f, ReportError)
    with pytest.raises(ReportError):
        verify.parse_dashboard(f, ReportError)


def test_report_gets_check_sheet(sample_jtl, sample_xml, tmp_path):
    std, dash = sample_xml
    out = tmp_path / 'r.xlsx'
    info = convert.create_excel_report(str(sample_jtl), str(out), standard_xml=str(std),
                                       dashboard_xml=str(dash))
    assert info['sheets'] == ['Сводка', 'График времени', 'Сверка', 'Исходные данные']
    assert info['verification']['ok']
    assert 'Расхождений нет' in load_workbook(out)['Сверка']['A2'].value


def test_report_flags_mismatch_on_top(sample_jtl, sample_xml, tmp_path):
    std, _ = sample_xml
    std.write_text(std.read_text(encoding='utf-8').replace('<max>', '<max>7', 1),
                   encoding='utf-8')
    out = tmp_path / 'r.xlsx'
    info = convert.create_excel_report(str(sample_jtl), str(out), standard_xml=str(std))
    assert not info['verification']['ok']
    assert any('расхожд' in w for w in info['warnings'])
    ws = load_workbook(out)['Сверка']
    assert ws['F5'].value == 'РАСХОЖДЕНИЕ'  # mismatches are sorted to the top


def test_without_xml_no_check_sheet(sample_jtl, tmp_path):
    info = convert.create_excel_report(str(sample_jtl), str(tmp_path / 'r.xlsx'))
    assert info['verification'] is None and 'Сверка' not in info['sheets']
