r"""report.toml: defaults for time zone, steps, SLA limits, comparison and exports.

    [report]
    timezone = "Europe/Moscow"     # local | UTC | Europe/Moscow | +05:00
    steps = '^\d{2}\.'             # regex of the labels treated as steps
    output_dir = "reports"         # where reports go when no path is given

    [compare]
    tolerance_pct = 10             # change of avg / p90 above this is a regression

    [export]
    formats = ["html", "csv"]      # extra outputs next to the Excel report

    [sla]                          # limits for every step
    p90_ms = 2000
    error_pct = 1.0
    [sla.total]                    # limits for the TOTAL row
    error_pct = 2.0
    [[sla.step]]                   # override for steps matching a regex
    match = '^02\.'
    p90_ms = 5000
"""
import os
import sys

import convert

try:  # Python 3.11+
    import tomllib
except ImportError:  # 3.9 / 3.10: the same parser as a package
    import tomli as tomllib

CONFIG_NAME = 'report.toml'
EXPORT_FORMATS = ('html', 'csv')
SECTIONS = {'report', 'compare', 'export', 'sla'}
REPORT_KEYS = {'timezone', 'steps', 'output_dir'}


class Config:
    def __init__(self):
        self.path = None
        self.timezone = None
        self.steps = None
        self.output_dir = None
        self.tolerance_pct = 10.0
        self.exports = []
        self.sla = None  # normalized by sla.normalize, or None


def find_config(*folders):
    """First report.toml among the given folders (None if there is none)."""
    seen = set()
    for folder in folders:
        if not folder:
            continue
        candidate = os.path.join(str(folder), CONFIG_NAME)
        if candidate not in seen and os.path.isfile(candidate):
            return candidate
        seen.add(candidate)
    return None


def load_config(path):
    """Parse and validate a config file. Raises convert.ReportError with a clear message."""
    try:
        with open(path, 'rb') as f:
            data = tomllib.load(f)
    except OSError as exc:
        raise convert.ReportError(f"Не удалось прочитать конфиг '{path}': {exc}")
    except tomllib.TOMLDecodeError as exc:
        raise convert.ReportError(f"Ошибка в конфиге '{path}': {exc}")

    unknown = set(data) - SECTIONS
    if unknown:
        raise convert.ReportError(
            f"В конфиге '{path}' неизвестные разделы: {', '.join(sorted(unknown))}. "
            f"Допустимы: {', '.join(sorted(SECTIONS))}.")

    cfg = Config()
    cfg.path = str(path)

    report = _table(data, 'report', path)
    bad = set(report) - REPORT_KEYS
    if bad:
        raise convert.ReportError(
            f"[report] в '{path}': неизвестные ключи {', '.join(sorted(bad))}. "
            f"Допустимы: {', '.join(sorted(REPORT_KEYS))}.")
    for key in REPORT_KEYS:
        if key in report and not isinstance(report[key], str):
            raise convert.ReportError(f"[report] {key} в '{path}' должен быть строкой.")
    cfg.timezone = report.get('timezone')
    cfg.steps = report.get('steps')
    cfg.output_dir = report.get('output_dir')

    compare = _table(data, 'compare', path)
    bad = set(compare) - {'tolerance_pct'}
    if bad:
        raise convert.ReportError(
            f"[compare] в '{path}': неизвестные ключи {', '.join(sorted(bad))}.")
    if 'tolerance_pct' in compare:
        cfg.tolerance_pct = _positive(compare['tolerance_pct'], 'compare.tolerance_pct', path)

    export = _table(data, 'export', path)
    bad = set(export) - {'formats'}
    if bad:
        raise convert.ReportError(
            f"[export] в '{path}': неизвестные ключи {', '.join(sorted(bad))}.")
    formats = export.get('formats', [])
    if not isinstance(formats, list) or any(f not in EXPORT_FORMATS for f in formats):
        raise convert.ReportError(
            f"[export] formats в '{path}': допустимы значения {', '.join(EXPORT_FORMATS)}.")
    cfg.exports = list(dict.fromkeys(formats))

    if 'sla' in data:
        import sla
        cfg.sla = sla.normalize(_table(data, 'sla', path), path)
    return cfg


def _table(data, name, path):
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise convert.ReportError(f"[{name}] в '{path}' должен быть таблицей.")
    return value


def _positive(value, name, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise convert.ReportError(f"{name} в '{path}' должен быть положительным числом.")
    return float(value)


def load_for(explicit, *folders):
    """Explicit --config path wins; otherwise report.toml from the first folder that has one."""
    if explicit:
        if not os.path.isfile(explicit):
            raise convert.ReportError(f"Конфиг не найден: '{explicit}'")
        return load_config(explicit)
    found = find_config(*folders)
    return load_config(found) if found else None


if __name__ == '__main__':  # python3 config.py [file]: validate a config
    target = sys.argv[1] if len(sys.argv) > 1 else CONFIG_NAME
    try:
        cfg = load_config(target)
    except convert.ReportError as exc:
        sys.exit(str(exc))
    print(f"{target}: OK")
