"""Preview of a JTL file for the terminal UI: quick statistics without building Excel."""
import os
import re
from collections import defaultdict

from rich.console import Group
from rich.table import Table
from rich.text import Text

from .errors import ReportError
from .jtl import parse_jtl_file, to_int
from .stats import DEFAULT_STEP_PATTERN, stats_of_rows
from .timeutil import format_duration

PREVIEW_ROW_LIMIT = 100_000
MAX_TABLE_ROWS = 14
BAR_WIDTH = 12


def summarize_jtl(path, limit=PREVIEW_ROW_LIMIT, step_pattern=DEFAULT_STEP_PATTERN):
    """Короткая сводка по JTL. Бросает ReportError, если файл не годится."""
    rows = parse_jtl_file(str(path), limit=limit + 1)
    truncated = len(rows) > limit
    rows = rows[:limit]
    if not rows:
        raise ReportError('в файле нет строк с данными')
    missing = {'timeStamp', 'elapsed', 'label'} - set(rows[0].keys())
    if missing:
        raise ReportError(
            f"нет колонок: {', '.join(sorted(missing))} (это точно JTL в формате CSV?)")

    grouped = defaultdict(list)
    for row in rows:
        grouped[row['label']].append(row)
    stats = [dict(stats_of_rows(r), label=label) for label, r in grouped.items()]
    total = stats_of_rows(rows)

    try:
        step_re = re.compile(step_pattern)
    except re.error:
        step_re = re.compile(DEFAULT_STEP_PATTERN)
    steps = [s for s in stats if step_re.match(s['label'])]
    shown = steps or stats  # без нумерованных шагов показываем метки как есть

    starts = [to_int(r.get('timeStamp')) for r in rows]
    ends = [to_int(r.get('timeStamp')) + to_int(r.get('elapsed')) for r in rows]
    return {
        'name': os.path.basename(str(path)),
        'size': os.path.getsize(path),
        'rows': len(rows),
        'truncated': truncated,
        'labels': len(stats),
        'errors': sum(1 for r in rows if str(r.get('success', '')).strip().upper() != 'TRUE'),
        'duration': format_duration(max(ends) - min(starts)),
        'avg': total['avg'],
        'p90': total['p90'],
        'throughput': total['throughput'],
        'rows_table': shown[:MAX_TABLE_ROWS],
        'hidden_labels': max(0, len(shown) - MAX_TABLE_ROWS),
        'is_steps': bool(steps),
    }


def human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024


def render_summary(info, accent='#d97757', dim='#8b8b8b', ok='#6fbf73', err='#e06c75'):
    """Rich-объект для панели предпросмотра."""
    head = Text()
    head.append(info['name'], style='bold')
    head.append(f"   {human_size(info['size'])}", style=dim)
    if info['truncated']:
        head.append(f"   (первые {info['rows']} строк)", style=dim)

    facts = Table.grid(padding=(0, 3))
    for _ in range(4):
        facts.add_column()
    errors_style = err if info['errors'] else ok
    facts.add_row(
        Text.assemble(('выборок  ', dim), (f"{info['rows']}", 'bold')),
        Text.assemble(('меток  ', dim), (f"{info['labels']}", 'bold')),
        Text.assemble(('ошибок  ', dim), (f"{info['errors']}", f'bold {errors_style}')),
        Text.assemble(('длительность  ', dim), (info['duration'], 'bold')),
    )

    table = Table(box=None, pad_edge=False, expand=True, header_style=dim,
                  show_edge=False, padding=(0, 1))
    table.add_column('шаг' if info['is_steps'] else 'метка', no_wrap=True,
                     overflow='ellipsis', ratio=1)
    table.add_column('n', justify='right')
    table.add_column('avg, мс', justify='right')
    table.add_column('p90', justify='right')
    table.add_column('err %', justify='right')
    table.add_column('', width=BAR_WIDTH, no_wrap=True)

    peak = max((s['avg'] for s in info['rows_table']), default=0) or 1
    for s in info['rows_table']:
        bar = '#' * max(1, round(s['avg'] / peak * BAR_WIDTH)) if s['avg'] else ''
        err_style = err if s['error_pct'] else dim
        table.add_row(s['label'], str(s['samples']), str(s['avg']), str(s['p90']),
                      Text(f"{s['error_pct']:.1f}", style=err_style), Text(bar, style=accent))

    parts = [head, Text(''), facts, Text(''), table]
    if info['hidden_labels']:
        parts.append(Text(f"... и еще {info['hidden_labels']} меток", style=dim))
    return Group(*parts)


def summarize_xml(path, error_cls=ReportError):
    """Сколько меток внутри standardResults.xml / dashBoard_jmeter.xml."""
    from . import verify
    name = os.path.basename(str(path))
    parser = verify.parse_dashboard if 'dash' in name.lower() else verify.parse_standard_results
    data = parser(str(path), error_cls)
    return {'name': name, 'size': os.path.getsize(path), 'labels': len(data),
            'values': sum(len(v) for v in data.values())}


def render_xml_summary(info, dim='#8b8b8b'):
    text = Text()
    text.append(info['name'], style='bold')
    text.append(f"   {human_size(info['size'])}\n\n", style=dim)
    text.append('меток  ', style=dim)
    text.append(f"{info['labels']}", style='bold')
    text.append('     значений для сверки  ', style=dim)
    text.append(f"{info['values']}", style='bold')
    text.append('\n\nЭтот файл будет использован для сверки расчета с цифрами JMeter.',
                style=dim)
    return text
