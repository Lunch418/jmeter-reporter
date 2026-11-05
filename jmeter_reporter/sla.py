"""SLA limits and the PASS / FAIL verdict for a run."""
import re

from .errors import ReportError
from .stats import DEFAULT_STEP_PATTERN

# limit name -> (key in stats, kind). 'max' = the value must not exceed the limit,
# 'min' = the value must not be below it.
LIMITS = {
    'avg_ms': ('avg', 'max'),
    'median_ms': ('median', 'max'),
    'p90_ms': ('p90', 'max'),
    'p95_ms': ('p95', 'max'),
    'p99_ms': ('p99', 'max'),
    'max_ms': ('max', 'max'),
    'error_pct': ('error_pct', 'max'),
    'min_throughput': ('throughput', 'min'),
}
SCOPES = ('steps', 'all')


def _limits(table, where, path):
    result = {}
    for key, value in table.items():
        if key not in LIMITS:
            raise ReportError(
                f"{where} в '{path}': неизвестное ограничение '{key}'. "
                f"Допустимы: {', '.join(LIMITS)}.")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ReportError(
                f"{where}.{key} в '{path}' должно быть неотрицательным числом.")
        result[key] = float(value)
    return result


def normalize(raw, path='report.toml'):
    """Validate the [sla] table. A typo in a limit must fail loudly, not silently pass."""
    raw = dict(raw)
    scope = raw.pop('scope', 'steps')
    if scope not in SCOPES:
        raise ReportError(f"sla.scope в '{path}': допустимо {', '.join(SCOPES)}.")
    total_raw = raw.pop('total', {})
    steps_raw = raw.pop('step', [])
    if not isinstance(total_raw, dict):
        raise ReportError(f"[sla.total] в '{path}' должен быть таблицей.")
    if not isinstance(steps_raw, list) or any(not isinstance(x, dict) for x in steps_raw):
        raise ReportError(f"[[sla.step]] в '{path}' должен быть массивом таблиц.")

    overrides = []
    for index, item in enumerate(steps_raw, 1):
        item = dict(item)
        pattern = item.pop('match', None)
        if not isinstance(pattern, str) or not pattern:
            raise ReportError(f"[[sla.step]] #{index} в '{path}': нужно поле match.")
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise ReportError(
                f"[[sla.step]] #{index} в '{path}': некорректное выражение '{pattern}': {exc}")
        limits = _limits(item, f'sla.step #{index}', path)
        if not limits:
            raise ReportError(f"[[sla.step]] #{index} в '{path}': нет ограничений.")
        overrides.append({'match': pattern, 'regex': regex, 'limits': limits})

    sla = {'scope': scope,
           'defaults': _limits(raw, 'sla', path),
           'total': _limits(total_raw, 'sla.total', path),
           'overrides': overrides}
    if not sla['defaults'] and not sla['total'] and not overrides:
        raise ReportError(f"[sla] в '{path}': не задано ни одного ограничения.")
    return sla


class Verdict:
    def __init__(self, rows):
        self.rows = rows
        self.failed = [r for r in rows if not r['ok']]
        self.passed = not self.failed

    @property
    def checked(self):
        return len(self.rows)

    @property
    def failed_labels(self):
        return list(dict.fromkeys(r['label'] for r in self.failed))


def _check(label, stats, limits, rows):
    for name, limit in limits.items():
        key, kind = LIMITS[name]
        actual = stats[key]
        ok = actual <= limit if kind == 'max' else actual >= limit
        rows.append({'label': label, 'limit': name, 'bound': limit, 'kind': kind,
                     'actual': actual, 'ok': ok})


def evaluate(run, sla, step_pattern=DEFAULT_STEP_PATTERN):
    """Check a stats.Run against normalized SLA. Raises ReportError if nothing was checked."""
    try:
        step_re = re.compile(step_pattern)
    except re.error as exc:
        raise ReportError(f"Некорректное регулярное выражение шагов: {exc}")

    uses_errors = any('error_pct' in lim for lim in
                      [sla['defaults'], sla['total'], *[o['limits'] for o in sla['overrides']]])
    if uses_errors and not run.has_success:
        raise ReportError(
            "В JTL нет колонки 'success': процент ошибок посчитать нельзя, а в SLA есть "
            "error_pct. Включите jmeter.save.saveservice.successful=true или уберите error_pct.")

    rows = []
    for label, stats in run.labels.items():
        in_scope = sla['scope'] == 'all' or step_re.match(label)
        limits = dict(sla['defaults']) if in_scope else {}
        for override in sla['overrides']:
            if override['regex'].match(label):
                limits.update(override['limits'])
        if limits:
            _check(label, stats, limits, rows)
    if sla['total']:
        _check('TOTAL', run.total, sla['total'], rows)
    if not rows:
        raise ReportError(
            'Ни одно ограничение SLA не применилось: ни один шаг не подошел под правила. '
            'Проверьте steps и match.')
    return Verdict(rows)


def format_verdict(verdict, width=100):
    """Plain-text table for a console / log."""
    lines = []
    for row in verdict.rows:
        mark = 'PASS' if row['ok'] else 'FAIL'
        sign = '<=' if row['kind'] == 'max' else '>='
        actual = f"{row['actual']:.2f}".rstrip('0').rstrip('.') if isinstance(
            row['actual'], float) else str(row['actual'])
        bound = f"{row['bound']:g}"
        lines.append(f"{mark}  {row['label'][:50]:<50}  {row['limit']:<15} "
                     f"{actual} {sign} {bound}")
    status = 'PASS' if verdict.passed else 'FAIL'
    lines.append(f"{status}: проверено {verdict.checked}, нарушений {len(verdict.failed)}")
    return '\n'.join(lines)
