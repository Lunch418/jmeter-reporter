"""The statistics engine against an independent reference (the Java algorithm, step by step)."""
import math

from hypothesis import given, settings
from hypothesis import strategies as st

from jmeter_reporter import stats
from jmeter_reporter.stats import percentile


def jmeter_percent_point(values, p):
    """StatCalculator.getPercentPoint: target = Math.round(count * p); walk the sorted values."""
    values = sorted(values)
    target = math.floor(len(values) * p + 0.5)
    for v in values:
        target -= 1
        if target <= 0:
            return v
    return 0


elapsed_lists = st.lists(st.integers(min_value=0, max_value=60_000), min_size=1, max_size=300)


@given(elapsed_lists, st.sampled_from([0.5, 0.9, 0.95, 0.99]))
@settings(max_examples=300, deadline=None)
def test_percentile_equals_jmeter_algorithm(values, p):
    assert percentile(sorted(values), p) == jmeter_percent_point(values, p)


@given(elapsed_lists)
@settings(max_examples=200, deadline=None)
def test_histogram_engine_equals_sorted_list_formulas(values):
    """The memory-light engine gives the same numbers as the textbook sorted-list one."""
    acc = stats._new_acc()
    for i, v in enumerate(values):
        stats._feed(acc, v, 1_700_000_000_000 + i, True, 1, 0)
    got = stats._finalize(acc)
    ordered = sorted(values)
    assert got['avg'] == sum(values) // len(values)
    assert got['median'] == percentile(ordered, 0.5)
    assert got['p90'] == percentile(ordered, 0.9)
    assert got['p95'] == percentile(ordered, 0.95)
    assert got['p99'] == percentile(ordered, 0.99)
    assert (got['min'], got['max']) == (ordered[0], ordered[-1])


@given(elapsed_lists)
@settings(max_examples=100, deadline=None)
def test_percentiles_are_ordered(values):
    acc = stats._new_acc()
    for i, v in enumerate(values):
        stats._feed(acc, v, i, True, 0, 0)
    r = stats._finalize(acc)
    assert r['min'] <= r['median'] <= r['p90'] <= r['p95'] <= r['p99'] <= r['max']


def test_hand_computed_odd_sample_counts(tmp_path):
    """Numbers worked out by hand with Math.round (half up), not produced by this code.

    5 samples 10,20,30,40,50: median target round(2.5)=3 -> 30; p90 round(4.5)=5 -> 50.
    9 samples 1..9: median round(4.5)=5 -> 5; p90 round(8.1)=8 -> 8; p99 round(8.91)=9 -> 9.
    """
    rows = []
    t = 1_700_000_000_000
    for label, values in (('A', [10, 20, 30, 40, 50]), ('B', list(range(1, 10)))):
        for v in values:
            rows.append(f'{t},{v},{label},200,true,1\n')
            t += 1000
    path = tmp_path / 'odd.jtl'
    path.write_text('timeStamp,elapsed,label,responseCode,success,bytes\n' + ''.join(rows))
    run = stats.load_run(str(path))
    a, b = run.labels['A'], run.labels['B']
    assert (a['median'], a['p90'], a['avg']) == (30, 50, 30)
    assert (b['median'], b['p90'], b['p99'], b['avg']) == (5, 8, 9, 5)
