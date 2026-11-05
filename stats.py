"""Streaming statistics from a JTL file.

The Excel report keeps every row in memory (it writes them to the "raw data" sheet).
Everything else (SLA check, run comparison, HTML/CSV export) only needs aggregates,
so it reads the file row by row and keeps one integer per sample. Formulas are the
same functions as in convert.py, so the numbers are identical to the report.
"""
import convert


class Run:
    """Aggregates of one test run: per label and total."""

    def __init__(self, path, rows, labels, total, first_ts, last_ts):
        self.path = path
        self.rows = rows
        self.labels = labels      # label -> stats dict (same keys as convert.collect_stats)
        self.total = total
        self.first_ts = first_ts  # epoch ms of the first request start
        self.last_ts = last_ts    # epoch ms of the last request end

    @property
    def duration_ms(self):
        return self.last_ts - self.first_ts

    def steps(self, pattern):
        """Labels matching the step regex, in file order."""
        import re
        try:
            step_re = re.compile(pattern)
        except re.error as exc:
            raise convert.ReportError(
                f"Некорректное регулярное выражение шагов '{pattern}': {exc}")
        return [label for label in self.labels if step_re.match(label)]


def _new_acc():
    return {'elapsed': [], 'start': None, 'end': None, 'errors': 0, 'bytes': 0, 'sent': 0}


def _feed(acc, elapsed, ts, ok, size, sent):
    acc['elapsed'].append(elapsed)
    end = ts + elapsed
    acc['start'] = ts if acc['start'] is None else min(acc['start'], ts)
    acc['end'] = end if acc['end'] is None else max(acc['end'], end)
    if not ok:
        acc['errors'] += 1
    acc['bytes'] += size
    acc['sent'] += sent


def _finalize(acc):
    values = sorted(acc['elapsed'])
    n = len(values)
    duration = (acc['end'] - acc['start']) / 1000.0
    return {
        'samples': n,
        'avg': convert.average(values),
        'median': convert.percentile(values, 0.50),
        'p90': convert.percentile(values, 0.90),
        'p95': convert.percentile(values, 0.95),
        'p99': convert.percentile(values, 0.99),
        'min': values[0],
        'max': values[-1],
        'error_pct': acc['errors'] / n * 100 if n else 0,
        'throughput': n / duration if duration > 0 else 0,
        'received_kb': acc['bytes'] / 1024 / duration if duration > 0 else 0,
        'sent_kb': acc['sent'] / 1024 / duration if duration > 0 else 0,
    }


def load_run(path, limit=None):
    """Read a JTL and return a Run. Raises convert.ReportError on unusable input."""
    per_label = {}
    total = _new_acc()
    rows = 0
    checked = False
    for row in convert.iter_jtl_rows(str(path), limit):
        if not checked:
            missing = {'timeStamp', 'elapsed', 'label'} - set(row.keys())
            if missing:
                raise convert.ReportError(
                    f"В '{path}' нет обязательных колонок: {', '.join(sorted(missing))}.\n"
                    f"Найдены: {', '.join(row.keys())}")
            checked = True
        elapsed = convert.to_int(row.get('elapsed'))
        ts = convert.to_int(row.get('timeStamp'))
        ok = str(row.get('success', '')).strip().upper() == 'TRUE'
        size = convert.to_int(row.get('bytes'))
        sent = convert.to_int(row.get('sentBytes'))
        acc = per_label.get(row['label'])
        if acc is None:
            acc = per_label[row['label']] = _new_acc()
        _feed(acc, elapsed, ts, ok, size, sent)
        _feed(total, elapsed, ts, ok, size, sent)
        rows += 1
    if not rows:
        raise convert.ReportError(f"Не удалось прочитать данные из JTL файла '{path}' - файл пуст.")
    labels = {label: dict(_finalize(acc), label=label) for label, acc in per_label.items()}
    return Run(str(path), rows, labels, dict(_finalize(total), label='TOTAL'),
               total['start'], total['end'])
