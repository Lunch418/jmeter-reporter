"""Comparison of two runs: what got better or worse between a baseline and a new run."""
import convert

DEFAULT_TOLERANCE_PCT = 10.0
ERROR_TOLERANCE_PP = 0.01  # error rate may rise by this many percentage points at most


def _delta(base, new):
    """Relative change in percent; None when the baseline is zero."""
    if base == 0:
        return None
    return (new - base) / base * 100.0


def _status(base, new, tolerance):
    """regression / improvement / same for a time metric."""
    delta = _delta(base, new)
    if delta is None:
        return 'same' if new == 0 else 'regression'
    if delta > tolerance:
        return 'regression'
    if delta < -tolerance:
        return 'improvement'
    return 'same'


class Comparison:
    def __init__(self, base, new, tolerance, rows, only_base, only_new):
        self.base = base
        self.new = new
        self.tolerance = tolerance
        self.rows = rows
        self.only_base = only_base
        self.only_new = only_new

    def count(self, status):
        return sum(1 for r in self.rows if r['status'] == status)

    @property
    def regressions(self):
        return [r for r in self.rows if r['status'] == 'regression']

    @property
    def has_regressions(self):
        return bool(self.regressions)


def compare_runs(base, new, step_pattern=convert.DEFAULT_STEP_PATTERN,
                 tolerance=DEFAULT_TOLERANCE_PCT, steps_only=True):
    """Compare two stats.Run objects label by label (steps only by default) plus TOTAL.

    A row is a regression if avg or p90 grew by more than `tolerance` percent or the
    error rate grew; an improvement if avg or p90 fell by more than that and nothing
    got worse; otherwise 'same'.
    """
    if tolerance < 0:
        raise convert.ReportError('Допуск сравнения не может быть отрицательным.')
    wanted = new.steps(step_pattern) if steps_only else list(new.labels)
    # Labels are matched without spaces at the edges, like in the XML cross-check.
    base_by_label = {label.strip(): s for label, s in base.labels.items()}
    rows = []
    only_new = []
    for label in wanted:
        stats_new = new.labels[label]
        stats_base = base_by_label.get(label.strip())
        if stats_base is None:
            only_new.append(label)
            continue
        rows.append(_row(label, stats_base, stats_new, tolerance))
    new_labels = {label.strip() for label in new.labels}
    base_candidates = base.steps(step_pattern) if steps_only else list(base.labels)
    only_base = [label for label in base_candidates if label.strip() not in new_labels]
    rows.append(_row('TOTAL', base.total, new.total, tolerance))
    return Comparison(base, new, tolerance, rows, only_base, only_new)


def _row(label, base, new, tolerance):
    avg_status = _status(base['avg'], new['avg'], tolerance)
    p90_status = _status(base['p90'], new['p90'], tolerance)
    errors_up = new['error_pct'] - base['error_pct'] > ERROR_TOLERANCE_PP
    statuses = {avg_status, p90_status}
    if 'regression' in statuses or errors_up:
        status = 'regression'
    elif 'improvement' in statuses:
        status = 'improvement'
    else:
        status = 'same'
    return {
        'label': label, 'status': status,
        'avg_base': base['avg'], 'avg_new': new['avg'],
        'avg_delta': _delta(base['avg'], new['avg']),
        'p90_base': base['p90'], 'p90_new': new['p90'],
        'p90_delta': _delta(base['p90'], new['p90']),
        'err_base': base['error_pct'], 'err_new': new['error_pct'],
        'samples_base': base['samples'], 'samples_new': new['samples'],
    }


STATUS_TEXT = {'regression': 'хуже', 'improvement': 'лучше', 'same': 'без изменений'}


def format_delta(value):
    return 'n/a' if value is None else f'{value:+.1f}%'


def format_comparison(cmp):
    """Plain-text summary for a console / log."""
    lines = [f"допуск {cmp.tolerance:g}%: хуже {cmp.count('regression')}, "
             f"лучше {cmp.count('improvement')}, без изменений {cmp.count('same')}"]
    for row in cmp.rows:
        if row['status'] == 'regression':
            lines.append(f"  хуже: {row['label'][:46]}: avg {row['avg_base']} -> "
                         f"{row['avg_new']} ({format_delta(row['avg_delta'])}), p90 "
                         f"{row['p90_base']} -> {row['p90_new']} "
                         f"({format_delta(row['p90_delta'])})"
                         + (f", ошибки {row['err_base']:.1f}% -> {row['err_new']:.1f}%"
                            if row['err_new'] - row['err_base'] > ERROR_TOLERANCE_PP else ''))
    if cmp.only_new:
        lines.append(f"  только в новом прогоне: {len(cmp.only_new)} меток")
    if cmp.only_base:
        lines.append(f"  только в базовом прогоне: {len(cmp.only_base)} меток")
    return '\n'.join(lines)


def write_comparison_xlsx(cmp, path):
    """Separate workbook with one sheet 'Сравнение' (the main report is not touched)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = 'Сравнение'
    thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                  top=Side(style='thin'), bottom=Side(style='thin'))
    head_fill = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
    fills = {'regression': PatternFill(start_color='F8CBAD', end_color='F8CBAD',
                                       fill_type='solid'),
             'improvement': PatternFill(start_color='E2F0D9', end_color='E2F0D9',
                                        fill_type='solid'),
             'same': None}

    ws['A1'] = 'Сравнение двух прогонов'
    ws['A1'].font = Font(bold=True, size=16)
    ws.merge_cells('A1:J1')
    info = [('Базовый прогон', cmp.base.path), ('Новый прогон', cmp.new.path),
            ('Допуск', f'{cmp.tolerance:g}%'),
            ('Итог', f"хуже: {cmp.count('regression')}, лучше: {cmp.count('improvement')}, "
                     f"без изменений: {cmp.count('same')}")]
    for offset, (key, value) in enumerate(info, start=3):
        ws.cell(row=offset, column=1, value=key).font = Font(bold=True)
        ws.cell(row=offset, column=2, value=value)

    headers = ['Label', 'Average (база)', 'Average (новый)', 'Average, %',
               'p90 (база)', 'p90 (новый)', 'p90, %', 'Ошибки % (база)',
               'Ошибки % (новый)', 'Итог']
    header_row = 8
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col, value=header)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = head_fill
        cell.border = thin
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    for r, row in enumerate(cmp.rows, start=header_row + 1):
        values = [row['label'], row['avg_base'], row['avg_new'], row['avg_delta'],
                  row['p90_base'], row['p90_new'], row['p90_delta'],
                  row['err_base'], row['err_new'], STATUS_TEXT[row['status']]]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=r, column=col, value='n/a' if value is None else value)
            cell.border = thin
            cell.alignment = Alignment(horizontal='left' if col in (1, 10) else 'right')
            if col in (4, 7) and value is not None:
                cell.number_format = '+0.0;-0.0;0.0'
            if col in (8, 9):
                cell.number_format = '0.00'
            if fills[row['status']]:
                cell.fill = fills[row['status']]
        if row['label'] == 'TOTAL':
            for col in range(1, len(headers) + 1):
                ws.cell(row=r, column=col).font = Font(bold=True)

    last = header_row + len(cmp.rows) + 2
    for title, labels in (('Только в новом прогоне', cmp.only_new),
                          ('Только в базовом прогоне', cmp.only_base)):
        if labels:
            ws.cell(row=last, column=1, value=title).font = Font(bold=True)
            for offset, label in enumerate(labels, 1):
                ws.cell(row=last + offset, column=1, value=label)
            last += len(labels) + 2

    for col, width in enumerate([44, 14, 14, 12, 12, 12, 10, 14, 14, 16], 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = ws.cell(row=header_row + 1, column=2)
    try:
        wb.save(path)
    except OSError as exc:
        raise convert.ReportError(f"Не удалось сохранить '{path}': {exc}")
