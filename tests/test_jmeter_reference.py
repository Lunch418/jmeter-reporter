"""Our numbers against a REAL JMeter 5.6.3 run (see samples/jmeter-5.6.3/README.md).

The expected values were produced by JMeter's own classes, not by this project.
"""
import csv
import json
from pathlib import Path

import pytest

from jmeter_reporter import stats

REF = Path(__file__).resolve().parent.parent / 'samples' / 'jmeter-5.6.3'


@pytest.fixture(scope='module')
def run():
    return stats.load_run(str(REF / 'odd_counts.jtl'))


def expected_rows():
    with open(REF / 'expected_statcalculator.tsv', encoding='utf-8') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def ours(run, label):
    return run.total if label == 'TOTAL' else run.labels[label]


def test_sample_counts_are_odd_as_intended(run):
    counts = sorted(s['samples'] for s in run.labels.values())
    assert counts == [5, 7, 9, 11, 13] and all(c % 2 for c in counts)


@pytest.mark.parametrize('row', expected_rows(), ids=lambda r: r['label'])
def test_matches_jmeter_statcalculator(run, row):
    got = ours(run, row['label'])
    assert got['samples'] == int(row['samples'])
    assert got['avg'] == int(row['mean'])
    for column, key in (('median', 'median'), ('p90', 'p90'), ('p95', 'p95'),
                        ('p99', 'p99'), ('min', 'min'), ('max', 'max')):
        assert got[key] == int(row[column]), (row['label'], key)


def test_matches_jmeter_dashboard_where_methods_agree(run):
    data = json.loads((REF / 'dashboard_statistics.json').read_text(encoding='utf-8'))
    for name, stat in data.items():
        got = ours(run, 'TOTAL' if name == 'Total' else name)
        assert got['samples'] == stat['sampleCount']
        assert got['error_pct'] == pytest.approx(stat['errorPct'])
        assert got['median'] == stat['medianResTime']
        assert (got['min'], got['max']) == (stat['minResTime'], stat['maxResTime'])
        assert got['avg'] == int(stat['meanResTime'])  # JMeter's mean is a float; ours truncates
