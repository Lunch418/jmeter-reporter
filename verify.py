"""Cross-check of JTL-computed statistics against Jenkins/JMeter XML artifacts.

standardResults.xml  - valid XML, one <api> per label with samples/average/min/
                       median/ninetieth/ninetyFifth/max/errors.
dashBoard_jmeter.xml - NOT valid XML (tags look like <01. Step name>), so it is
                       read line by line: sections <average>, <median>,
                       <percentile> with currentBuildAvg/Med/90Line/95Line.
"""
import re
import xml.etree.ElementTree as ET

# our stats key -> (label in report, tolerance)
STANDARD_FIELDS = {
    'samples': ('samples', 0),
    'average': ('avg', 0),
    'min': ('min', 0),
    'median': ('median', 0),
    'ninetieth': ('p90', 0),
    'ninetyFifth': ('p95', 0),
    'max': ('max', 0),
    'errors': ('error_pct', 0.01),
}
DASHBOARD_FIELDS = {
    'currentBuildAvg': ('avg', 0),
    'currentBuildMed': ('median', 0),
    'currentBuild90Line': ('p90', 0),
    'currentBuild95Line': ('p95', 0),
}

_FIELD_RE = re.compile(r'^\s*<(currentBuild\w+)>\s*(-?[\d.]+)\s*</\1>\s*$')
_SECTION_RE = re.compile(r'^<(average|median|percentile)>\s*$')
_LABEL_OPEN_RE = re.compile(r'^\s*<(.+)>\s*$')


def _number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return int(value) if value.is_integer() else value


def parse_standard_results(path, error_cls=ValueError):
    """label -> {stats key: number} from standardResults.xml."""
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise error_cls(f"Не удалось прочитать '{path}' как XML: {exc}")
    result = {}
    for api in root.iter('api'):
        label = (api.findtext('uri') or '').strip()
        if not label:
            continue
        values = {}
        for tag, (key, _tol) in STANDARD_FIELDS.items():
            number = _number(api.findtext(tag))
            if number is not None:
                values[key] = number
        result[label] = values
    if not result:
        raise error_cls(f"В '{path}' нет данных <api>: это точно standardResults.xml?")
    return result


def parse_dashboard(path, error_cls=ValueError):
    """label -> {stats key: number} from dashBoard_jmeter.xml (not valid XML)."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError as exc:
        raise error_cls(f"Не удалось прочитать '{path}': {exc}")
    result = {}
    section = None
    label = None
    for line in lines:
        m = _SECTION_RE.match(line.strip())
        if m:
            section = m.group(1)
            label = None
            continue
        if line.strip() in ('</average>', '</median>', '</percentile>'):
            section = None
            continue
        if section is None:
            continue
        m = _FIELD_RE.match(line)
        if m:
            if label is not None and m.group(1) in DASHBOARD_FIELDS:
                key = DASHBOARD_FIELDS[m.group(1)][0]
                number = _number(m.group(2))
                if number is not None:
                    result.setdefault(label, {})[key] = number
            continue
        m = _LABEL_OPEN_RE.match(line)
        if m and not m.group(1).startswith('/'):
            label = m.group(1)
    if not result:
        raise error_cls(f"В '{path}' нет данных: это точно dashBoard_jmeter.xml?")
    return result


def _tolerance(key):
    for _tag, (k, tol) in {**STANDARD_FIELDS, **DASHBOARD_FIELDS}.items():
        if k == key:
            return tol
    return 0


def compare(stats, expected, source):
    """Сравнить посчитанную статистику с данными из XML.

    stats    - список словарей collect_stats(...) + 'label'
    expected - label -> {key: number} из parse_*
    Возвращает список строк: label, metric, source, expected, actual, ok.
    Метки, которых нет в JTL, дают строку с actual=None и ok=False.
    """
    # Метки сравниваем без пробелов по краям: в JTL бывает 'Раздел ' с хвостовым пробелом.
    by_label = {s['label'].strip(): s for s in stats}
    rows = []
    for label, values in expected.items():
        actual_stats = by_label.get(label.strip())
        for key, exp in values.items():
            if actual_stats is None:
                rows.append({'label': label, 'metric': key, 'source': source,
                             'expected': exp, 'actual': None, 'ok': False})
                continue
            act = actual_stats[key]
            rows.append({'label': label, 'metric': key, 'source': source,
                         'expected': exp, 'actual': act,
                         'ok': abs(act - exp) <= _tolerance(key) + 1e-9})
    return rows


def summarize(rows):
    mismatches = [r for r in rows if not r['ok']]
    return {'checked': len(rows), 'mismatches': len(mismatches),
            'ok': not mismatches}
