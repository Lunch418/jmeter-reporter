import pytest

from jmeter_reporter import config
from jmeter_reporter import convert
from jmeter_reporter import sla


def norm(**kw):
    return sla.normalize(kw)


RUN = [('01. A', 100, True)] * 9 + [('01. A', 900, True)] + [('02. B', 50, True), ('02. B', 60, False),
                                                              ('sub', 5000, True)]


def test_pass_and_fail(make_run):
    run = make_run(RUN)
    verdict = sla.evaluate(run, norm(p90_ms=1000, error_pct=60))
    assert verdict.passed and verdict.checked == 4  # two steps x two limits
    # p90 of '01. A' is 100 by the JMeter formula (index round(10 * 0.9) - 1 = 8)
    assert sla.evaluate(run, norm(p90_ms=100)).passed
    verdict = sla.evaluate(run, norm(p90_ms=99))
    assert not verdict.passed
    assert verdict.failed_labels == ['01. A']


def test_boundary_is_inclusive(make_run):
    run = make_run([('01. A', 100, True)] * 3)
    assert sla.evaluate(run, norm(p90_ms=100)).passed
    assert not sla.evaluate(run, norm(p90_ms=99)).passed


def test_sub_requests_are_not_checked_by_default(make_run):
    run = make_run(RUN)
    labels = {r['label'] for r in sla.evaluate(run, norm(max_ms=10 ** 6)).rows}
    assert labels == {'01. A', '02. B'}
    labels = {r['label'] for r in sla.evaluate(run, norm(max_ms=10 ** 6, scope='all')).rows}
    assert 'sub' in labels


def test_override_applies_to_matching_step(make_run):
    run = make_run([('01. A', 500, True), ('02. B', 500, True)])
    rules = sla.normalize({'p90_ms': 100, 'step': [{'match': r'^02\.', 'p90_ms': 1000}]})
    verdict = sla.evaluate(run, rules)
    assert verdict.failed_labels == ['01. A']


def test_override_can_check_a_label_outside_scope(make_run):
    run = make_run([('sub', 500, True)])
    rules = sla.normalize({'step': [{'match': '^sub', 'p90_ms': 100}]})
    assert sla.evaluate(run, rules).failed_labels == ['sub']


def test_total_limits(make_run):
    run = make_run([('01. A', 10, True), ('01. A', 10, False)])
    rules = sla.normalize({'total': {'error_pct': 10}})
    verdict = sla.evaluate(run, rules)
    assert [r['label'] for r in verdict.rows] == ['TOTAL'] and not verdict.passed


def test_min_throughput_is_a_lower_bound(make_run):
    run = make_run([('01. A', 10, True)] * 5)  # 5 samples in ~4 s -> ~1 req/s
    assert sla.evaluate(run, norm(min_throughput=0.5)).passed
    assert not sla.evaluate(run, norm(min_throughput=50)).passed


def test_nothing_checked_is_an_error(make_run):
    run = make_run([('sub', 10, True)])
    with pytest.raises(convert.ReportError, match='Ни одно'):
        sla.evaluate(run, norm(p90_ms=100))


@pytest.mark.parametrize('raw,match', [
    ({}, 'не задано'),
    ({'p90': 100}, 'неизвестное ограничение'),
    ({'p90_ms': -1}, 'неотрицательным'),
    ({'p90_ms': 'fast'}, 'неотрицательным'),
    ({'p90_ms': True}, 'неотрицательным'),
    ({'p90_ms': 1, 'scope': 'bogus'}, 'scope'),
    ({'p90_ms': 1, 'total': 5}, 'таблицей'),
    ({'p90_ms': 1, 'step': {'match': 'x'}}, 'массивом'),
    ({'p90_ms': 1, 'step': [{'p90_ms': 5}]}, 'match'),
    ({'p90_ms': 1, 'step': [{'match': '(', 'p90_ms': 5}]}, 'некорректное'),
    ({'p90_ms': 1, 'step': [{'match': 'x'}]}, 'нет ограничений'),
])
def test_normalize_rejects_mistakes(raw, match):
    with pytest.raises(convert.ReportError, match=match):
        sla.normalize(raw)


def test_typo_in_config_fails_loudly(tmp_path):
    path = tmp_path / 'report.toml'
    path.write_text('[sla]\np90ms = 100\n', encoding='utf-8')
    with pytest.raises(convert.ReportError, match='p90ms'):
        config.load_config(str(path))


def test_format_verdict(make_run):
    run = make_run([('01. A', 500, True)])
    text = sla.format_verdict(sla.evaluate(run, norm(p90_ms=100, error_pct=5)))
    assert 'FAIL  01. A' in text and 'PASS  01. A' in text
    assert text.splitlines()[-1].startswith('FAIL: проверено 2, нарушений 1')
