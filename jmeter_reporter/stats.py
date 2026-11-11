"""Streaming statistics from a JTL file.

This is the ONLY place where the numbers are computed: the Excel report, the SLA check,
the comparison and the exports all use load_run(). Memory is O(number of distinct
elapsed values), not O(samples): every label keeps a histogram {elapsed_ms: count}.
"""
import math
import re
from collections import Counter

from . import jtl
from .errors import ReportError

# Шаги сценария по умолчанию: 'NN. Название'.
DEFAULT_STEP_PATTERN = r'^\d{2}\.'

# Метки с id внутри ('GET /order/123') дают сотни тысяч уникальных меток и гигабайты памяти.
MAX_LABELS = 10_000


class Run:
    """Aggregates of one test run: per label and total."""

    def __init__(self, path, rows, labels, total, first_ts, last_ts, errors=0, has_success=True):
        self.path = path
        self.errors = errors            # number of failed samples
        self.has_success = has_success  # the JTL has a 'success' column
        self.notes = []  # warnings from reading (e.g. a truncated last line)
        self.rows = rows
        self.labels = labels      # label -> stats dict (same keys as stats_of_rows)
        self.total = total
        self.first_ts = first_ts  # epoch ms of the first request start
        self.last_ts = last_ts    # epoch ms of the last request end

    @property
    def duration_ms(self):
        return self.last_ts - self.first_ts

    def steps(self, pattern):
        """Labels matching the step regex, in file order."""
        try:
            step_re = re.compile(pattern)
        except re.error as exc:
            raise ReportError(
                f"Некорректное регулярное выражение шагов '{pattern}': {exc}")
        return [label for label in self.labels if step_re.match(label)]


def percentile(sorted_values, fraction):
    """Перцентиль по формуле JMeter (StatCalculator.getPercentPoint) на отсортированном списке.

    Индекс = Math.round(n * p) - 1. Math.round в Java округляет половину ВВЕРХ, а
    встроенный round() в Python - к четному (round(2.5) == 2), поэтому здесь floor(x + 0.5).

    Медиана - тот же вызов с fraction=0.5, а НЕ statistics.median(): JMeter берет один
    элемент, а statistics.median на чётном n усредняет два соседних.
    """
    n = len(sorted_values)
    return sorted_values[max(0, math.floor(n * fraction + 0.5) - 1)]


def average(values):
    """Среднее по формуле JMeter: целочисленное деление, без округления."""
    return sum(values) // len(values) if values else 0


def _percentiles_from_histogram(histogram, n, fractions):
    """Те же перцентили, но по гистограмме {мс: сколько раз}: один проход по ключам."""
    targets = sorted((max(0, math.floor(n * f + 0.5) - 1), f) for f in fractions)
    result, cumulative, i = {}, 0, 0
    for value in sorted(histogram):
        cumulative += histogram[value]
        while i < len(targets) and targets[i][0] < cumulative:
            result[targets[i][1]] = value
            i += 1
        if i == len(targets):
            break
    return result


def _new_acc():
    return {'hist': Counter(), 'n': 0, 'sum': 0, 'start': None, 'end': None,
            'errors': 0, 'bytes': 0, 'sent': 0}


def _feed(acc, elapsed, ts, ok, size, sent):
    acc['hist'][elapsed] += 1
    acc['n'] += 1
    acc['sum'] += elapsed
    end = ts + elapsed
    acc['start'] = ts if acc['start'] is None else min(acc['start'], ts)
    acc['end'] = end if acc['end'] is None else max(acc['end'], end)
    if not ok:
        acc['errors'] += 1
    acc['bytes'] += size
    acc['sent'] += sent


def _merge(into, acc):
    into['hist'].update(acc['hist'])
    into['n'] += acc['n']
    into['sum'] += acc['sum']
    into['start'] = acc['start'] if into['start'] is None else min(into['start'], acc['start'])
    into['end'] = acc['end'] if into['end'] is None else max(into['end'], acc['end'])
    into['errors'] += acc['errors']
    into['bytes'] += acc['bytes']
    into['sent'] += acc['sent']


def _finalize(acc):
    n = acc['n']
    hist = acc['hist']
    # Длительность = от начала первого замера до КОНЦА последнего: max(timeStamp) - min(timeStamp)
    # теряет время выполнения последнего запроса и завышает throughput.
    duration = (acc['end'] - acc['start']) / 1000.0
    pct = _percentiles_from_histogram(hist, n, (0.50, 0.90, 0.95, 0.99))
    return {
        'samples': n,
        'avg': acc['sum'] // n if n else 0,
        'median': pct[0.50],
        'p90': pct[0.90],
        'p95': pct[0.95],
        'p99': pct[0.99],
        'min': min(hist),
        'max': max(hist),
        'error_pct': acc['errors'] / n * 100 if n else 0,
        'throughput': n / duration if duration > 0 else 0,
        'received_kb': acc['bytes'] / 1024 / duration if duration > 0 else 0,
        'sent_kb': acc['sent'] / 1024 / duration if duration > 0 else 0,
    }


def stats_of_rows(rows):
    """Aggregates for a list of JTL row dicts (one label or the whole test)."""
    acc = _new_acc()
    for r in rows:
        _feed(acc, jtl.to_int(r.get('elapsed')), jtl.to_int(r.get('timeStamp')),
              str(r.get('success', '')).strip().upper() == 'TRUE',
              jtl.to_int(r.get('bytes')), jtl.to_int(r.get('sentBytes')))
    return _finalize(acc)


def load_run(path, limit=None):
    """Read a JTL and return a Run. Raises ReportError on unusable input."""
    per_label = {}
    rows = 0
    checked = False
    has_success = True
    notes = []
    for row in jtl.iter_jtl_rows(str(path), limit, notes):
        if not checked:
            missing = {'timeStamp', 'elapsed', 'label'} - set(row.keys())
            if missing:
                raise ReportError(
                    f"В '{path}' нет обязательных колонок: {', '.join(sorted(missing))}.\n"
                    f"Найдены: {', '.join(row.keys())}")
            checked = True
            has_success = 'success' in row
        acc = per_label.get(row['label'])
        if acc is None:
            if len(per_label) >= MAX_LABELS:
                raise ReportError(
                    f"В '{path}' больше {MAX_LABELS} уникальных меток (строка {rows + 2}). "
                    f"Вероятно, в метке есть id или время: настройте имена семплеров в JMeter "
                    f"или сгруппируйте их регулярным выражением.")
            acc = per_label[row['label']] = _new_acc()
        _feed(acc, int(row['elapsed']), int(row['timeStamp']),
              str(row.get('success', '')).strip().upper() == 'TRUE',
              jtl.to_int(row.get('bytes')), jtl.to_int(row.get('sentBytes')))
        rows += 1
    if not rows:
        raise ReportError(f"Не удалось прочитать данные из JTL файла '{path}' - файл пуст.")
    total = _new_acc()
    for acc in per_label.values():
        _merge(total, acc)
    labels = {label: dict(_finalize(acc), label=label) for label, acc in per_label.items()}
    run = Run(str(path), rows, labels, dict(_finalize(total), label='TOTAL'),
              total['start'], total['end'], total['errors'], has_success)
    run.notes = notes
    return run
