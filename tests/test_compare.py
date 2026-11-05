import pytest
from openpyxl import load_workbook

import compare
import convert
import stats


def run_of(make_run, avg, name, err=0, extra=()):
    n = 10
    samples = [('01. Step', avg, i >= err) for i in range(n)] + list(extra)
    return make_run(samples, name)


def test_identical_runs_are_same(sample_jtl):
    run = stats.load_run(sample_jtl)
    cmp = compare.compare_runs(run, run)
    assert not cmp.has_regressions and cmp.count('same') == len(cmp.rows)
    assert cmp.only_base == [] and cmp.only_new == []
    assert cmp.rows[-1]['label'] == 'TOTAL'


def test_regression_and_improvement(make_run):
    base = make_run([('01. A', 100, True), ('02. B', 100, True)], 'b.jtl')
    new = make_run([('01. A', 150, True), ('02. B', 50, True)], 'n.jtl')
    cmp = compare.compare_runs(base, new)
    by = {r['label']: r for r in cmp.rows}
    assert by['01. A']['status'] == 'regression'
    assert by['01. A']['avg_delta'] == pytest.approx(50)
    assert by['02. B']['status'] == 'improvement'
    assert by['02. B']['avg_delta'] == pytest.approx(-50)
    assert cmp.has_regressions and cmp.regressions[0]['label'] == '01. A'


def test_tolerance_decides(make_run):
    base = make_run([('01. A', 100, True)], 'b.jtl')
    new = make_run([('01. A', 108, True)], 'n.jtl')
    assert compare.compare_runs(base, new, tolerance=10).rows[0]['status'] == 'same'
    assert compare.compare_runs(base, new, tolerance=5).rows[0]['status'] == 'regression'


def test_error_rate_growth_is_a_regression(make_run):
    base = make_run([('01. A', 100, True)] * 4, 'b.jtl')
    new = make_run([('01. A', 100, True)] * 3 + [('01. A', 100, False)], 'n.jtl')
    row = compare.compare_runs(base, new).rows[0]
    assert row['status'] == 'regression' and row['avg_delta'] == 0


def test_zero_baseline(make_run):
    base = make_run([('01. A', 0, True)], 'b.jtl')
    assert compare.compare_runs(base, make_run([('01. A', 0, True)], 'n.jtl')).rows[0]['status'] == 'same'
    row = compare.compare_runs(base, make_run([('01. A', 5, True)], 'n2.jtl')).rows[0]
    assert row['status'] == 'regression' and row['avg_delta'] is None
    assert compare.format_delta(None) == 'n/a'


def test_labels_only_on_one_side(make_run):
    base = make_run([('01. A', 10, True), ('02. Old', 10, True)], 'b.jtl')
    new = make_run([('01. A', 10, True), ('03. New', 10, True)], 'n.jtl')
    cmp = compare.compare_runs(base, new)
    assert cmp.only_new == ['03. New'] and cmp.only_base == ['02. Old']
    assert [r['label'] for r in cmp.rows] == ['01. A', 'TOTAL']


def test_labels_match_ignoring_edge_spaces(make_run):
    base = make_run([('01. A ', 100, True)], 'b.jtl')
    new = make_run([('01. A', 100, True)], 'n.jtl')
    assert compare.compare_runs(base, new).only_new == []


def test_all_labels_mode(make_run):
    base = make_run([('01. A', 10, True), ('sub', 10, True)], 'b.jtl')
    new = make_run([('01. A', 10, True), ('sub', 10, True)], 'n.jtl')
    labels = [r['label'] for r in compare.compare_runs(base, new, steps_only=False).rows]
    assert labels == ['01. A', 'sub', 'TOTAL']


def test_negative_tolerance_rejected(make_run):
    run = make_run([('01. A', 1, True)])
    with pytest.raises(convert.ReportError):
        compare.compare_runs(run, run, tolerance=-1)


def test_format_comparison(make_run):
    base = make_run([('01. A', 100, True)], 'b.jtl')
    new = make_run([('01. A', 200, True), ('02. X', 1, True)], 'n.jtl')
    text = compare.format_comparison(compare.compare_runs(base, new))
    assert 'хуже 2' in text and '01. A' in text and '+100.0%' in text
    assert 'только в новом' in text


def test_comparison_workbook(make_run, tmp_path):
    base = make_run([('01. A', 100, True), ('02. B', 100, True)], 'b.jtl')
    new = make_run([('01. A', 200, True), ('02. B', 10, True), ('03. C', 5, True)], 'n.jtl')
    out = tmp_path / 'cmp.xlsx'
    compare.write_comparison_xlsx(compare.compare_runs(base, new), out)
    wb = load_workbook(out)
    assert wb.sheetnames == ['Сравнение']
    ws = wb['Сравнение']
    assert ws['A1'].value == 'Сравнение двух прогонов'
    rows = {ws.cell(row=r, column=1).value: r for r in range(9, 14)}
    assert ws.cell(row=rows['01. A'], column=10).value == 'хуже'
    assert ws.cell(row=rows['02. B'], column=10).value == 'лучше'
    assert ws.cell(row=rows['01. A'], column=4).value == pytest.approx(100)
    assert ws.cell(row=rows['01. A'], column=1).fill.start_color.rgb.endswith('F8CBAD')
    assert ws.cell(row=rows['02. B'], column=1).fill.start_color.rgb.endswith('E2F0D9')
    texts = [c.value for row in ws.iter_rows() for c in row if c.value]
    assert 'Только в новом прогоне' in texts and '03. C' in texts


def test_comparison_write_error(make_run, tmp_path):
    run = make_run([('01. A', 1, True)])
    with pytest.raises(convert.ReportError, match='сохранить'):
        compare.write_comparison_xlsx(compare.compare_runs(run, run), tmp_path / 'no' / 'x.xlsx')
