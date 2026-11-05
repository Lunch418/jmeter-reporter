#!/usr/bin/env python3
"""Преобразует результаты нагрузочного тестирования JMeter (.jtl) в Excel-отчёт.

Использование:
    python3 convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx
    python3 convert.py jmeter.jtl report.xlsx
    python3 convert.py jmeter.jtl report.xlsx --tz Europe/Moscow

Время в отчёте по умолчанию - локальное время той машины, где запущен скрипт.
Переопределить: --tz Europe/Moscow | --tz UTC | --tz +05:00 | --tz local
"""
import os
import re
import sys

from . import errors as _errors
from . import jtl as _jtl
from . import safety as _safety
from . import stats as stats_module
from . import timeutil as _timeutil
from . import verify

# Лимит строк листа Excel (xlsx). Лист 'Исходные данные' обрезается по нему,
# иначе openpyxl падает на большом JTL уже в момент сохранения.
EXCEL_MAX_ROWS = 1_048_576

DEFAULT_STEP_PATTERN = stats_module.DEFAULT_STEP_PATTERN


# ---------------------------------------------------------------- отчёт ----

def _import_openpyxl():
    """openpyxl нужен только для Excel-отчета; SLA, сравнение и экспорт работают без него."""
    try:
        from openpyxl import Workbook
        from openpyxl.chart import BarChart, Reference
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise _errors.ReportError(
            "Для построения Excel-отчета нужен пакет openpyxl (pip install openpyxl).\n"
            "Без него работают проверка SLA, сравнение и экспорт: python3 cli.py --help")
    return (Workbook, BarChart, Reference, Alignment, Border, Font, PatternFill, Side,
            get_column_letter)


_UMASK = os.umask(0)
os.umask(_UMASK)


def _temp_path(output_file):
    """Уникальный временный файл рядом с отчетом (на той же файловой системе: replace атомарен)."""
    import tempfile
    folder = os.path.dirname(os.path.abspath(output_file))
    fd, path = tempfile.mkstemp(dir=folder, prefix='.report-', suffix='.tmp')
    os.close(fd)
    os.chmod(path, 0o666 & ~_UMASK)  # mkstemp делает 0600, а отчет должен быть как обычный файл
    return path


def create_excel_report(jtl_file, output_file, tz=None, step_pattern=DEFAULT_STEP_PATTERN,
                        standard_xml=None, dashboard_xml=None, include_raw_data=True,
                        archive=None):
    """Строит xlsx-отчёт. Возвращает словарь со сводкой (для CLI и UI).

    include_raw_data=False пропускает лист 'Исходные данные' (он нужен не всем и делает файл
    в разы больше). Остальные листы при этом получаются теми же самыми. Лист пишется потоком,
    память от числа строк не зависит.

    archive - функция без аргументов; вызывается, когда новый отчет готов и вот-вот
    заменит старый (чтобы перенести старый в историю). Ее результат попадает в info['archived'].
    """
    (Workbook, BarChart, Reference, Alignment, Border, Font, PatternFill, Side,
     get_column_letter) = _import_openpyxl()
    from . import rawsheet  # нужен openpyxl, поэтому не на верхнем уровне

    # Единственный расчет: stats.load_run читает файл потоком. Порядок меток - как в JTL
    # (он совпадает с порядком шагов сценария). Начало и конец теста - min/max, а не первая
    # и последняя строка: JMeter пишет строки в порядке ЗАВЕРШЕНИЯ замеров.
    run = stats_module.load_run(jtl_file)
    warnings = list(run.notes)
    n_rows, n_errors, has_success = run.rows, run.errors, run.has_success
    stats = list(run.labels.values())
    total_stats = {k: v for k, v in run.total.items() if k != 'label'}
    first_ts, last_ts = run.first_ts, run.last_ts

    if not has_success:
        warnings.append("в JTL нет колонки 'success' - все замеры будут учтены как ошибочные")

    # Сверка с XML-артефактами Jenkins (необязательная).
    check_rows = []
    if standard_xml:
        check_rows += verify.compare(
            stats, verify.parse_standard_results(standard_xml, _errors.ReportError),
            'standardResults.xml')
    if dashboard_xml:
        check_rows += verify.compare(
            stats, verify.parse_dashboard(dashboard_xml, _errors.ReportError),
            'dashBoard_jmeter.xml')
    check = verify.summarize(check_rows) if (standard_xml or dashboard_xml) else None
    if check and not check['ok']:
        warnings_after = (f"сверка с XML: {check['mismatches']} расхождений из "
                          f"{check['checked']} (список в консоли; в Excel-отчет не попадает)")
    else:
        warnings_after = None

    tz_label = _timeutil.timezone_label(first_ts, tz)
    start_time = _timeutil.format_timestamp(first_ts, tz)
    end_time = _timeutil.format_timestamp(last_ts, tz)
    duration_str = _timeutil.format_duration(last_ts - first_ts)

    wb = Workbook()

    header_font_bold_11 = Font(bold=True, size=11)
    header_font_bold_16 = Font(bold=True, size=16)
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                         top=Side(style='thin'), bottom=Side(style='thin'))
    header_fill_blue = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
    header_font_white = Font(bold=True, size=11, color='FFFFFF')
    label_fill = PatternFill(start_color='DDEBF7', end_color='DDEBF7', fill_type='solid')
    value_fill = PatternFill(start_color='FFFFFF', end_color='FFFFFF', fill_type='solid')
    total_fill = PatternFill(start_color='E2F0D9', end_color='E2F0D9', fill_type='solid')

    # ================= ЛИСТ 1: СВОДКА =================
    ws1 = wb.active
    ws1.title = 'Сводка'

    ws1['A1'] = 'Отчет по результатам нагрузочного тестирования'
    ws1['A1'].font = header_font_bold_16
    ws1.merge_cells('A1:E1')

    summary_rows = [
        (3, 'Файл JTL', os.path.basename(jtl_file), f'Начало тестирования ({tz_label})', start_time),
        (4, 'Всего выборок', n_rows, f'Окончание тестирования ({tz_label})', end_time),
        (5, 'Ошибок', n_errors, 'Длительность', duration_str),
    ]
    for row, left_label, left_value, right_label, right_value in summary_rows:
        for column, value, fill in (
            ('A', left_label, label_fill), ('B', left_value, value_fill),
            ('D', right_label, label_fill), ('E', right_value, value_fill),
        ):
            cell = ws1[f'{column}{row}']
            cell.value = value
            cell.font = header_font_bold_11
            cell.fill = fill

    headers = ['Label', '# Samples', 'Average', 'Median', '90% Line', '95% Line', '99% Line',
               'Min', 'Max', 'Error %', 'Throughput', 'Received KB/sec', 'Sent KB/sec']

    for col, header in enumerate(headers, 1):
        cell = ws1.cell(row=7, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill_blue
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    def stat_values(s):
        return [s['label'], s['samples'], s['avg'], s['median'], s['p90'], s['p95'], s['p99'],
                s['min'], s['max'], s['error_pct'], s['throughput'], s['received_kb'], s['sent_kb']]

    row_idx = 8
    for s in stats:
        for col, val in enumerate(stat_values(s), 1):
            cell = ws1.cell(row=row_idx, column=col, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='left' if col == 1 else 'right')
            if col >= 10:
                cell.number_format = '0.000'
        row_idx += 1

    for col, val in enumerate(stat_values(dict(total_stats, label='TOTAL')), 1):
        cell = ws1.cell(row=row_idx, column=col, value=val)
        cell.font = header_font_bold_11
        cell.fill = total_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='left' if col == 1 else 'right')
        if col >= 10:
            cell.number_format = '0.000'

    for col, width in enumerate([30, 12, 12, 12, 12, 12, 12, 10, 10, 12, 15, 18, 15], 1):
        ws1.column_dimensions[get_column_letter(col)].width = width

    # ================= ЛИСТ 2: ГРАФИК ВРЕМЕНИ =================
    ws2 = wb.create_sheet('График времени')
    ws2['A1'] = 'Агрегированный график времени выполнения шагов'
    ws2['A1'].font = header_font_bold_16
    ws2.merge_cells('A1:J1')

    graph_headers = ['Label', '# Samples', 'Average', 'Median', '90% Line', '95% Line',
                     '99% Line', 'Min', 'Max', 'Error %']
    HEADER_ROW = 3
    FIRST_DATA_ROW = HEADER_ROW + 1

    for col, header in enumerate(graph_headers, 1):
        cell = ws2.cell(row=HEADER_ROW, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill_blue
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')

    # Любой шаг вида 'NN. ...', а не жёстко 01-10: одиннадцатый шаг
    # раньше молча исчезал и из таблицы, и из диаграммы.
    try:
        step_re = re.compile(step_pattern)
    except re.error as exc:
        raise _errors.ReportError(f"Некорректное регулярное выражение шагов '{step_pattern}': {exc}")
    main_steps = [s for s in stats if step_re.match(s['label'])]

    r_idx = FIRST_DATA_ROW
    for s in main_steps:
        values = [s['label'], s['samples'], s['avg'], s['median'], s['p90'],
                  s['p95'], s['p99'], s['min'], s['max'], s['error_pct']]
        for col, val in enumerate(values, 1):
            cell = ws2.cell(row=r_idx, column=col, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='left' if col == 1 else 'right')
            if col == 10:
                cell.number_format = '0.000'
        r_idx += 1

    if main_steps:
        last_data_row = FIRST_DATA_ROW + len(main_steps) - 1

        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "Время выполнения шагов (мс)"
        chart.x_axis.title = 'Время, мс'
        chart.y_axis.title = 'Шаги'

        # Ряды берутся с HEADER_ROW (titles_from_data=True) по last_data_row.
        # Раньше верхняя граница считалась как 2 + len(main_steps), то есть
        # на строку меньше, и последний шаг ('10. Выход из системы') просто
        # не попадал в диаграмму, а подписи категорий уезжали на шаг.
        chart.add_data(Reference(ws2, min_col=3, min_row=HEADER_ROW, max_row=last_data_row),
                       titles_from_data=True)
        chart.add_data(Reference(ws2, min_col=5, min_row=HEADER_ROW, max_row=last_data_row),
                       titles_from_data=True)
        chart.set_categories(Reference(ws2, min_col=1, min_row=FIRST_DATA_ROW,
                                       max_row=last_data_row))
        chart.height = 12
        chart.width = 20
        ws2.add_chart(chart, "A" + str(r_idx + 2))

    for col in range(1, len(graph_headers) + 1):
        lengths = [len(str(ws2.cell(row=r, column=col).value or ''))
                   for r in range(HEADER_ROW, r_idx)]
        ws2.column_dimensions[get_column_letter(col)].width = min(max(lengths or [8]) + 2, 30)

    # ================= ЛИСТ 3: ИСХОДНЫЕ ДАННЫЕ =================
    raw_stream = None
    if include_raw_data:
        ws3 = wb.create_sheet('Исходные данные')
        numeric_columns = {'timeStamp', 'elapsed', 'bytes', 'sentBytes', 'grpThreads',
                           'allThreads', 'Latency', 'IdleTime', 'Connect'}
        raw_limit = EXCEL_MAX_ROWS - 1
        truncated = n_rows - raw_limit

        # Заголовок строит openpyxl, строки данных пишутся потоком прямо в архив xlsx
        # (rawsheet.py): память не зависит от числа строк.
        rows_iter = _jtl.iter_jtl_rows(jtl_file)
        raw_headers = list(next(rows_iter).keys())
        rows_iter = _jtl.iter_jtl_rows(jtl_file)
        for col, header in enumerate(raw_headers, 1):
            cell = ws3.cell(row=1, column=col, value=header)
            cell.font = header_font_white
            cell.fill = header_fill_blue
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')
        sample = ws3.cell(row=2, column=1, value=0)  # образец стиля ячейки данных
        sample.border = thin_border
        raw_stream = (rows_iter, wb._cell_styles.add(sample._style), numeric_columns,
                      raw_headers, min(n_rows, raw_limit))

        if truncated > 0:
            warnings.append(f"лист 'Исходные данные' обрезан: {truncated} строк "
                            f"не поместились в лимит Excel ({EXCEL_MAX_ROWS} строк)")

    if warnings_after:
        warnings.append(warnings_after)

    for sheet in wb.worksheets:
        if sheet.title != 'Исходные данные':
            _safety.neutralize_formulas(sheet)

    # Сначала во временный файл, потом одним переименованием: если сборка упала,
    # прежний отчет остается на месте. Старая версия копируется в историю до замены, а не
    # переносится: пути отчета нет пустого момента. Имена временных файлов уникальны
    # (два процесса с одним -o не затирают друг друга).
    tmp = None
    archived = []
    try:
        try:
            tmp = _temp_path(output_file)
            wb.save(tmp)
            if raw_stream:
                rows_iter, style, numeric_columns, raw_headers, total_rows = raw_stream
                tmp_full = _temp_path(output_file)
                try:
                    _, cut = rawsheet.fill_sheet(
                        tmp, tmp_full, wb.sheetnames.index('Исходные данные') + 1,
                        rows_iter, style, numeric_columns, raw_headers, total_rows)
                    os.replace(tmp_full, tmp)
                finally:
                    if os.path.exists(tmp_full):
                        os.remove(tmp_full)
                if cut:
                    warnings.append(f"{cut} ячеек листа 'Исходные данные' обрезано до "
                                    f"{rawsheet.MAX_CELL_CHARS} символов (лимит Excel)")
            if archive is not None:
                archived = archive()
            rawsheet.atomic_replace(tmp, output_file)
        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
    except OSError as exc:
        raise _errors.ReportError(f"Не удалось сохранить '{output_file}': {exc}")

    return {
        'output': output_file,
        'sheets': list(wb.sheetnames),
        'rows': n_rows,
        'steps': len(main_steps),
        'labels': len(stats),
        'errors': n_errors,
        'raw_data': include_raw_data,
        'timezone': tz_label,
        'start': start_time,
        'end': end_time,
        'duration': duration_str,
        'verification': check,
        'warnings': warnings,
        'run': run,
        'archived': archived,
    }


# ------------------------------------------------------------------ CLI ----

USAGE = (
    "Использование:\n"
    "  python3 convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx\n"
    "  python3 convert.py jmeter.jtl report.xlsx\n"
    "\n"
    "Опции:\n"
    "  --standard F   standardResults.xml: сверить расчёт с цифрами JMeter.\n"
    "  --dashboard F  dashBoard_jmeter.xml: то же, по average/median/90/95.\n"
    "                 (в четырёхаргументной форме оба файла берутся из позиций)\n"
    "  --no-raw-data  не добавлять лист 'Исходные данные': для очень больших JTL\n"
    "                 (лимит строк Excel, память). Остальные листы те же.\n"
    "  --raw-data     добавить лист 'Исходные данные' (по умолчанию; перекрывает конфиг).\n"
    "  --version      версия программы.\n"
    "\n"
    "Коды выхода: 0 - готово; 2 - ошибка входных данных, файла или конфига;\n"
    "3 - внутренняя ошибка программы (подробности в stderr).\n"
    "  --config F     report.toml с умолчаниями (пояс, шаги); по умолчанию берется\n"
    "                 report.toml из текущей папки, если он есть.\n"
    "  --steps RE  Регулярное выражение для шагов на листе 'График времени'.\n"
    "              По умолчанию '^\\d{2}\\.' (метки вида '01. ...').\n"
    "  --tz ПОЯС   Часовой пояс для меток времени в отчёте.\n"
    "              По умолчанию - локальное время машины.\n"
    "              Примеры: --tz Europe/Moscow, --tz UTC, --tz +05:00\n"
)


VALUE_OPTIONS = ('--tz', '--steps', '--standard', '--dashboard', '--config')


def parse_args(argv):
    """Разбор командной строки. Возвращает словарь параметров; ошибки - _errors.UsageError/_errors.ReportError."""
    options = {'--tz': None, '--steps': None, '--standard': None, '--dashboard': None,
               '--config': None, '--raw-data': None}
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('--no-raw-data', '--raw-data'):
            options['--raw-data'] = (arg == '--raw-data')
            i += 1
            continue
        name, eq, inline = arg.partition('=')
        if name in VALUE_OPTIONS:
            if eq:
                options[name] = inline
                i += 1
            elif i + 1 < len(argv):
                options[name] = argv[i + 1]
                i += 2
            else:
                raise _errors.UsageError(f"Ошибка: у {name} не указано значение.\n\n" + USAGE)
        else:
            positional.append(arg)
            i += 1

    # Две формы вызова: короткая (jtl, xlsx) и историческая четырёхаргументная
    # (jtl, dashBoard_jmeter.xml, standardResults.xml, xlsx). XML используются
    # для сверки расчёта с цифрами JMeter.
    if len(positional) == 2:
        jtl_file, output_file = positional
    elif len(positional) == 4:
        jtl_file, dashboard, standard, output_file = positional
        options['--dashboard'] = options['--dashboard'] or dashboard
        options['--standard'] = options['--standard'] or standard
    else:
        raise _errors.UsageError(USAGE)

    # report.toml (рядом с запуском или из --config) задает значения по умолчанию.
    from . import config
    cfg = config.load_for(options['--config'], os.getcwd())
    if cfg:
        options['--tz'] = options['--tz'] or cfg.timezone
        options['--steps'] = options['--steps'] or cfg.steps
        if options['--raw-data'] is None:
            options['--raw-data'] = cfg.include_raw_data
        options['keep_history'] = cfg.keep_history
    options['--steps'] = options['--steps'] or DEFAULT_STEP_PATTERN

    for path in (jtl_file, options['--standard'], options['--dashboard']):
        if path and not os.path.isfile(path):
            raise _errors.ReportError(f"Файл не найден: '{path}'")

    tz = _timeutil.resolve_timezone(options['--tz'])
    return {'jtl': jtl_file, 'output': output_file, 'tz': tz,
            'steps': options['--steps'], 'standard': options['--standard'],
            'dashboard': options['--dashboard'],
            'raw_data': True if options['--raw-data'] is None else options['--raw-data'],
            'keep_history': options.get('keep_history', True)}


def main(argv=None):
    """Точка входа. Коды выхода те же, что у cli.py: 0 - готово, 2 - ошибка входных данных."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if '-h' in argv or '--help' in argv:
        print(USAGE)
        return 0
    if '--version' in argv:
        from . import version
        print(f'jmeter-report {version.__version__}')
        return 0
    try:
        args = parse_args(argv)
        archive = None
        if args['keep_history']:
            from . import history
            archive = lambda: history.archive_existing(  # noqa: E731
                args['output'], copy_output=True)
        info = create_excel_report(
            args['jtl'], args['output'], tz=args['tz'], step_pattern=args['steps'],
            standard_xml=args['standard'], dashboard_xml=args['dashboard'],
            include_raw_data=args['raw_data'], archive=archive)
    except _errors.ReportError as exc:
        print(exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"{exc.strerror or exc}: {getattr(exc, 'filename', '') or ''}".strip(': '),
              file=sys.stderr)
        return 2
    except Exception:  # внутренняя ошибка: отдельный код, чтобы не путать со входными данными
        import traceback
        traceback.print_exc()
        print("Внутренняя ошибка программы (код выхода 3).", file=sys.stderr)
        return 3
    for warning in info['warnings']:
        print(f"Внимание: {warning}", file=sys.stderr)
    if args['keep_history']:
        history.record(args['output'], args['jtl'], info, None, info['archived'])
        for path in info['archived']:
            print(f"Прошлая версия сохранена: {path}")
    print(f"Файл '{info['output']}' успешно создан!")
    print(f"   Листы: {', '.join(info['sheets'])}")
    print(f"   Строк данных: {info['rows']}")
    print(f"   Время в отчёте: {info['timezone']}")
    if info['verification']:
        v = info['verification']
        print(f"   Сверка с XML: {'расхождений нет' if v['ok'] else str(v['mismatches']) + ' расхождений'}"
              f" (проверено {v['checked']})")
        for row in v['details'][:10]:
            print(f"      {row['label']} / {row['metric']} ({row['source']}): "
                  f"в XML {row['expected']}, по JTL {row['actual']}")
        if len(v['details']) > 10:
            print(f"      ... и еще {len(v['details']) - 10}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
