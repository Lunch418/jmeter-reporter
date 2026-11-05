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

from . import stats as stats_module
from . import verify
from .errors import ReportError, UsageError
from .jtl import JTL_ENCODING, iter_jtl_rows, parse_jtl_file, to_int  # noqa: F401
from .safety import FORMULA_TRIGGERS, csv_safe, neutralize_formulas  # noqa: F401
from .stats import average, percentile  # noqa: F401
from .timeutil import (FIXED_ZONES, format_duration, format_timestamp,  # noqa: F401
                       resolve_timezone, timezone_label, to_datetime)

# Выше этого числа строк отчет строится долго и держит весь JTL в памяти.
LARGE_FILE_ROWS = 200_000

# Лимит строк листа Excel (xlsx). Лист 'Исходные данные' обрезается по нему,
# иначе openpyxl падает на большом JTL уже в момент сохранения.
EXCEL_MAX_ROWS = 1_048_576

# Оценка памяти листа 'Исходные данные' (измерено на 40 тысячах строк, 17 колонок).
BYTES_PER_RAW_ROW = 8500

# Шаги сценария по умолчанию: 'NN. Название'.
DEFAULT_STEP_PATTERN = r'^\d{2}\.'


def collect_stats(rows):
    """Агрегаты по списку замеров (словари строк JTL). Формулы - в stats.py."""
    return stats_module.stats_of_rows(rows)


# ---------------------------------------------------------------- отчёт ----

def _import_openpyxl():
    """openpyxl нужен только для Excel-отчета; SLA, сравнение и экспорт работают без него."""
    try:
        from openpyxl import Workbook
        from openpyxl.chart import BarChart, Reference
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise ReportError(
            "Для построения Excel-отчета нужен пакет openpyxl (pip install openpyxl).\n"
            "Без него работают проверка SLA, сравнение и экспорт: python3 cli.py --help")
    return (Workbook, BarChart, Reference, Alignment, Border, Font, PatternFill, Side,
            get_column_letter)


def create_excel_report(jtl_file, output_file, tz=None, step_pattern=DEFAULT_STEP_PATTERN,
                        standard_xml=None, dashboard_xml=None, include_raw_data=True):
    """Строит xlsx-отчёт. Возвращает словарь со сводкой (для CLI и UI).

    include_raw_data=False пропускает лист 'Исходные данные': файл читается потоком
    (память не растет с размером JTL), а лимит строк Excel перестает быть проблемой.
    Остальные листы при этом получаются теми же самыми.
    """
    (Workbook, BarChart, Reference, Alignment, Border, Font, PatternFill, Side,
     get_column_letter) = _import_openpyxl()

    # Единственный расчет: stats.load_run читает файл потоком. Порядок меток - как в JTL
    # (он совпадает с порядком шагов сценария). Начало и конец теста - min/max, а не первая
    # и последняя строка: JMeter пишет строки в порядке ЗАВЕРШЕНИЯ замеров.
    run = stats_module.load_run(jtl_file)
    warnings = list(run.notes)
    n_rows, n_errors, has_success = run.rows, run.errors, run.has_success
    stats = list(run.labels.values())
    total_stats = {k: v for k, v in run.total.items() if k != 'label'}
    first_ts, last_ts = run.first_ts, run.last_ts

    if n_rows > LARGE_FILE_ROWS and include_raw_data:
        # Измерено: лист 'Исходные данные' стоит около 8 КБ памяти на строку (ячейки openpyxl).
        gb = n_rows * BYTES_PER_RAW_ROW / 1024 ** 3
        warnings.append(f"большой файл ({n_rows} строк): лист 'Исходные данные' займет "
                        f"около {gb:.1f} ГБ памяти и будет строиться долго. Отключите его: "
                        f"--no-raw-data (остальные листы те же, памяти нужно в десятки раз "
                        f"меньше). Проверка SLA, сравнение и экспорт (cli.py) читают файл потоком")
    if not has_success:
        warnings.append("в JTL нет колонки 'success' - все замеры будут учтены как ошибочные")

    # Сверка с XML-артефактами Jenkins (необязательная).
    check_rows = []
    if standard_xml:
        check_rows += verify.compare(
            stats, verify.parse_standard_results(standard_xml, ReportError),
            'standardResults.xml')
    if dashboard_xml:
        check_rows += verify.compare(
            stats, verify.parse_dashboard(dashboard_xml, ReportError),
            'dashBoard_jmeter.xml')
    check = verify.summarize(check_rows) if (standard_xml or dashboard_xml) else None
    if check and not check['ok']:
        warnings_after = (f"сверка с XML: {check['mismatches']} расхождений из "
                          f"{check['checked']} (см. лист 'Сверка')")
    else:
        warnings_after = None

    tz_label = timezone_label(first_ts, tz)
    start_time = format_timestamp(first_ts, tz)
    end_time = format_timestamp(last_ts, tz)
    duration_str = format_duration(last_ts - first_ts)

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
        raise ReportError(f"Некорректное регулярное выражение шагов '{step_pattern}': {exc}")
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

    # ================= ЛИСТ: СВЕРКА С XML =================
    if check_rows:
        ws_check = wb.create_sheet('Сверка')
        ws_check['A1'] = 'Сверка расчёта по JTL с артефактами Jenkins'
        ws_check['A1'].font = header_font_bold_16
        ws_check.merge_cells('A1:F1')
        verdict = ('Расхождений нет' if check['ok']
                   else f"Расхождений: {check['mismatches']} из {check['checked']}")
        ws_check['A2'] = f"Проверено значений: {check['checked']}. {verdict}."
        ws_check['A2'].font = header_font_bold_11
        bad_fill = PatternFill(start_color='F8CBAD', end_color='F8CBAD', fill_type='solid')
        ok_fill = PatternFill(start_color='E2F0D9', end_color='E2F0D9', fill_type='solid')
        check_headers = ['Label', 'Метрика', 'Источник', 'В XML', 'Посчитано по JTL', 'Результат']
        for col, header in enumerate(check_headers, 1):
            cell = ws_check.cell(row=4, column=col, value=header)
            cell.font = header_font_white
            cell.fill = header_fill_blue
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')
        # Расхождения наверх, чтобы их не пришлось искать.
        for r, row in enumerate(sorted(check_rows, key=lambda x: x['ok']), start=5):
            if row['actual'] is None:
                result = 'нет в JTL'
            else:
                result = 'OK' if row['ok'] else 'РАСХОЖДЕНИЕ'
            values = [row['label'], row['metric'], row['source'], row['expected'],
                      row['actual'] if row['actual'] is not None else '', result]
            for col, val in enumerate(values, 1):
                cell = ws_check.cell(row=r, column=col, value=val)
                cell.border = thin_border
                cell.fill = ok_fill if row['ok'] else bad_fill
        for col, width in enumerate([42, 14, 22, 12, 18, 14], 1):
            ws_check.column_dimensions[get_column_letter(col)].width = width

    # ================= ЛИСТ 3: ИСХОДНЫЕ ДАННЫЕ =================
    if include_raw_data:
        ws3 = wb.create_sheet('Исходные данные')
        numeric_columns = {'timeStamp', 'elapsed', 'bytes', 'sentBytes', 'grpThreads',
                           'allThreads', 'Latency', 'IdleTime', 'Connect'}
        raw_limit = EXCEL_MAX_ROWS - 1
        truncated = n_rows - raw_limit

        # Второй потоковый проход по файлу: список строк JTL в памяти не держим
        # (остаются только ячейки openpyxl).
        raw_headers = None
        for r_idx, row in enumerate(iter_jtl_rows(jtl_file), start=2):
            if r_idx - 1 > raw_limit:
                break
            if raw_headers is None:
                raw_headers = list(row.keys())
                for col, header in enumerate(raw_headers, 1):
                    cell = ws3.cell(row=1, column=col, value=header)
                    cell.font = header_font_white
                    cell.fill = header_fill_blue
                    cell.border = thin_border
                    cell.alignment = Alignment(horizontal='center')
            for col, header in enumerate(raw_headers, 1):
                value = row.get(header, '')
                # Числа записываются числами, иначе Excel показывает их как текст
                # и по ним нельзя ни отсортировать, ни построить формулу.
                if header in numeric_columns and str(value).strip().lstrip('-').isdigit():
                    value = int(value)
                cell = ws3.cell(row=r_idx, column=col, value=value)
                if type(value) is str and value.startswith(FORMULA_TRIGGERS):
                    cell.data_type = 's'
                cell.border = thin_border

        if truncated > 0:
            warnings.append(f"лист 'Исходные данные' обрезан: {truncated} строк "
                            f"не поместились в лимит Excel ({EXCEL_MAX_ROWS} строк)")

    if warnings_after:
        warnings.append(warnings_after)

    for sheet in wb.worksheets:
        if sheet.title != 'Исходные данные':
            neutralize_formulas(sheet)

    try:
        wb.save(output_file)
    except OSError as exc:
        raise ReportError(f"Не удалось сохранить '{output_file}': {exc}")

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
    """Разбор командной строки. Возвращает словарь параметров; ошибки - UsageError/ReportError."""
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
                raise UsageError(f"Ошибка: у {name} не указано значение.\n\n" + USAGE)
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
        raise UsageError(USAGE)

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
            raise ReportError(f"Файл не найден: '{path}'")

    tz = resolve_timezone(options['--tz'])
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
        archived = []
        if args['keep_history']:
            from . import history
            archived = history.archive_existing(args['output'])
        info = create_excel_report(
            args['jtl'], args['output'], tz=args['tz'], step_pattern=args['steps'],
            standard_xml=args['standard'], dashboard_xml=args['dashboard'],
            include_raw_data=args['raw_data'])
    except ReportError as exc:
        print(exc, file=sys.stderr)
        return 2
    for warning in info['warnings']:
        print(f"Внимание: {warning}", file=sys.stderr)
    if args['keep_history']:
        history.record(args['output'], args['jtl'], info, None, archived)
        for path in archived:
            print(f"Прошлая версия сохранена: {path}")
    print(f"Файл '{info['output']}' успешно создан!")
    print(f"   Листы: {', '.join(info['sheets'])}")
    print(f"   Строк данных: {info['rows']}")
    print(f"   Время в отчёте: {info['timezone']}")
    if info['verification']:
        v = info['verification']
        print(f"   Сверка с XML: {'расхождений нет' if v['ok'] else str(v['mismatches']) + ' расхождений'}"
              f" (проверено {v['checked']})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
