from collections import defaultdict

import pytest

import convert
import stats


def test_streaming_matches_report_formulas(sample_jtl):
    run = stats.load_run(sample_jtl)
    rows = convert.parse_jtl_file(str(sample_jtl))
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['label']].append(row)
    assert list(run.labels) == list(grouped)  # file order is kept
    for label, group in grouped.items():
        assert run.labels[label] == dict(convert.collect_stats(group), label=label)
    assert {k: v for k, v in run.total.items() if k != 'label'} == convert.collect_stats(rows)
    assert run.rows == len(rows)


def test_run_times(sample_jtl):
    run = stats.load_run(sample_jtl)
    assert run.first_ts == 1768471200000
    assert run.duration_ms > 0


def test_limit_reads_only_first_rows(sample_jtl):
    assert stats.load_run(sample_jtl, limit=10).rows == 10


def test_steps_filter(sample_jtl):
    run = stats.load_run(sample_jtl)
    assert len(run.steps(r'^\d{2}\.')) == 10
    assert run.steps(r'^ZZZ') == []
    with pytest.raises(convert.ReportError, match='регулярное'):
        run.steps('(')


def test_errors_counted(make_run):
    run = make_run([('a', 10, True), ('a', 20, False), ('a', 30, False)])
    assert run.labels['a']['error_pct'] == pytest.approx(200 / 3)
    assert run.total['samples'] == 3


def test_missing_success_column_counts_as_errors(tmp_path):
    f = tmp_path / 'x.jtl'
    f.write_text('timeStamp,elapsed,label\n1,10,a\n', encoding='utf-8')
    assert stats.load_run(f).labels['a']['error_pct'] == 100


@pytest.mark.parametrize('content,match', [
    ('timeStamp,elapsed,label\n', 'пуст'),
    ('a,b\n1,2\n', 'обязательных колонок'),
    ('<testResults/>', 'XML'),
])
def test_bad_files(tmp_path, content, match):
    f = tmp_path / 'bad.jtl'
    f.write_text(content, encoding='utf-8')
    with pytest.raises(convert.ReportError, match=match):
        stats.load_run(f)
