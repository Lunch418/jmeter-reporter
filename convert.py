#!/usr/bin/env python3
"""Преобразует результаты нагрузочного тестирования JMeter (.jtl) в Excel-отчёт.

Использование:
    python3 convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx
    python3 convert.py jmeter.jtl report.xlsx
    python3 convert.py jmeter.jtl report.xlsx --tz Europe/Moscow

Время в отчёте по умолчанию - локальное время той машины, где запущен скрипт.
Переопределить: --tz Europe/Moscow | --tz UTC | --tz +05:00 | --tz local
"""
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference

import verify

# Выше этого числа строк отчет строится долго и держит весь JTL в памяти.
LARGE_FILE_ROWS = 200_000

# Лимит строк листа Excel (xlsx). Лист 'Исходные данные' обрезается по нему,
# иначе openpyxl падает на большом JTL уже в момент сохранения.
EXCEL_MAX_ROWS = 1_048_576

# Шаги сценария по умолчанию: 'NN. Название'.
DEFAULT_STEP_PATTERN = r'^\d{2}\.'


class ReportError(Exception):
    """Ошибка входных данных или параметров; текст предназначен для пользователя."""


# ---------------------------------------------------------------- время ----

def resolve_timezone(spec):
    """Часовой пояс для отображения меток времени.

    None или 'local' -> локальный пояс машины (значение по умолчанию).
    'UTC', 'Europe/Moscow', 'Asia/Yekaterinburg' -> именованный пояс (нужен Python 3.9+).
    '+05:00', '-03:30', '+5' -> фиксированное смещение, работает на любом Python.
    """
    if spec is None or spec.strip().lower() == 'local':
        return None  # None => datetime.astimezone() возьмёт пояс машины

    spec = spec.strip()

    offset = re.fullmatch(r'(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?', spec, re.IGNORECASE)
    if offset:
        sign = 1 if offset.group(1) == '+' else -1
        delta = timedelta(hours=int(offset.group(2)), minutes=int(offset.group(3) or 0))
        return timezone(sign * delta)

    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        raise ReportError(
            f"Именованный часовой пояс '{spec}' требует Python 3.9+.\n"
            f"На более старой версии укажите смещение явно, например: --tz +03:00"
        )

    try:
        return ZoneInfo(spec)
    except Exception:
        raise ReportError(
            f"Неизвестный часовой пояс: '{spec}'.\n"
            f"Ожидается имя вида Europe/Moscow, UTC, либо смещение вида +05:00.\n"
            f"На Windows именованные пояса требуют пакета tzdata: pip install tzdata"
        )


def to_datetime(ts_ms, tz):
    """Метка времени JMeter (epoch в миллисекундах) -> datetime в поясе tz."""
    return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).astimezone(tz)


def format_timestamp(ts_ms, tz):
    """Читаемая метка времени: '21.07.2026 17:31:26.285'."""
    try:
        return to_datetime(ts_ms, tz).strftime('%d.%m.%Y %H:%M:%S.%f')[:-3]
    except (TypeError, ValueError, OSError, OverflowError):
        return 'N/A'


def timezone_label(ts_ms, tz):
    """Подпись пояса для шапки отчёта: 'UTC+03:00'.

    Смещение считается на момент самого теста, а не на 'сейчас', поэтому
    отчёт по летнему тесту, открытый зимой, всё равно подпишется правильно.
    """
    try:
        offset = to_datetime(ts_ms, tz).utcoffset()
    except (TypeError, ValueError, OSError, OverflowError):
        return 'UTC'
    if offset is None:
        return 'UTC'
    total_minutes = int(offset.total_seconds() // 60)
    sign = '+' if total_minutes >= 0 else '-'
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def format_duration(ms):
    """Длительность в формате '4 мин 51,430 сек' (с часами, если тест длинный)."""
    total_seconds = ms / 1000.0
    hours = int(total_seconds) // 3600
    minutes = (int(total_seconds) % 3600) // 60
    seconds = total_seconds - hours * 3600 - minutes * 60
    tail = f"{minutes} мин {seconds:.3f}".replace('.', ',') + " сек"
    return f"{hours} ч {tail}" if hours else tail


# ------------------------------------------------------------ разбор JTL ----

def to_int(value, default=0):
    """int() устойчивый к пустым и нечисловым ячейкам JTL.

    dict.get(key, 0) здесь не спасает: в JTL колонка часто присутствует,
    но пустая, и .get вернёт '' - int('') падает с ValueError.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def iter_jtl_rows(jtl_file, limit=None):
    """Построчное чтение JTL (CSV): память не растет с размером файла."""
    with open(jtl_file, 'r', encoding='utf-8', errors='replace', newline='') as f:
        head = f.read(200)
        f.seek(0)
        if head.lstrip().startswith('<'):
            raise ReportError(
                f"Файл '{jtl_file}' похож на JTL в формате XML, а скрипт читает CSV.\n"
                f"В JMeter выставьте jmeter.save.saveservice.output_format=csv "
                f"и перезапустите тест."
            )
        for index, row in enumerate(csv.DictReader(f)):
            if limit is not None and index >= limit:
                return
            yield row


def parse_jtl_file(jtl_file, limit=None):
    """Читает JTL (CSV) в список словарей. limit - максимум строк (для предпросмотра)."""
    return list(iter_jtl_rows(jtl_file, limit))


def percentile(sorted_values, fraction):
    """Перцентиль по формуле JMeter: индекс round(n * p) - 1.

    Медиана здесь - тот же самый вызов с fraction=0.5, а НЕ statistics.median():
    JMeter берёт один средний элемент, а statistics.median на чётном n
    усредняет два соседних. На реальных данных это расходится в разы
    (шаг '01. Home page': 121 у JMeter против 327 у statistics.median).
    """
    n = len(sorted_values)
    return sorted_values[max(0, round(n * fraction) - 1)]


def average(values):
    """Среднее по формуле JMeter: целочисленное деление, без округления.

    round(mean) даёт +1 мс примерно на половине шагов и расходится
    с цифрами в standardResults.xml, которые заказчик может сверять.
    """
    return sum(values) // len(values) if values else 0


def collect_stats(rows):
    """Агрегаты по одной группе замеров (один label либо весь тест)."""
    elapsed = sorted(to_int(r.get('elapsed')) for r in rows)
    starts = [to_int(r.get('timeStamp')) for r in rows]
    ends = [to_int(r.get('timeStamp')) + to_int(r.get('elapsed')) for r in rows]

    # Длительность = от начала первого замера до КОНЦА последнего.
    # max(timeStamp) - min(timeStamp) теряет время выполнения последнего
    # запроса, занижая длительность и завышая throughput.
    duration_sec = (max(ends) - min(starts)) / 1000.0
    errors = sum(1 for r in rows if str(r.get('success', '')).strip().upper() != 'TRUE')
    total_bytes = sum(to_int(r.get('bytes')) for r in rows)
    total_sent = sum(to_int(r.get('sentBytes')) for r in rows)
    n = len(rows)

    return {
        'samples': n,
        'avg': average(elapsed),
        'median': percentile(elapsed, 0.50),
        'p90': percentile(elapsed, 0.90),
        'p95': percentile(elapsed, 0.95),
        'p99': percentile(elapsed, 0.99),
        'min': elapsed[0],
        'max': elapsed[-1],
        'error_pct': errors / n * 100 if n else 0,
        'throughput': n / duration_sec if duration_sec > 0 else 0,
        'received_kb': total_bytes / 1024 / duration_sec if duration_sec > 0 else 0,
        'sent_kb': total_sent / 1024 / duration_sec if duration_sec > 0 else 0,
    }


# ---------------------------------------------------------------- отчёт ----

def create_excel_report(jtl_file, output_file, tz=None, step_pattern=DEFAULT_STEP_PATTERN,
                        standard_xml=None, dashboard_xml=None):
    """Строит xlsx-отчёт. Возвращает словарь со сводкой (для CLI и UI)."""
    jtl_data = parse_jtl_file(jtl_file)

    if not jtl_data:
        raise ReportError(f"Не удалось прочитать данные из JTL файла '{jtl_file}' - файл пуст.")

    missing = {'timeStamp', 'elapsed', 'label'} - set(jtl_data[0].keys())
    if missing:
        raise ReportError(
            f"В '{jtl_file}' нет обязательных колонок: {', '.join(sorted(missing))}.\n"
            f"Найдены: {', '.join(jtl_data[0].keys())}"
        )
    warnings = []
    if len(jtl_data) > LARGE_FILE_ROWS:
        warnings.append(f"большой файл ({len(jtl_data)} строк): отчет строится долго и требует "
                        f"много памяти; проверка SLA, сравнение и экспорт (cli.py) читают файл потоком")
    if 'success' not in jtl_data[0]:
        warnings.append("в JTL нет колонки 'success' - все замеры будут учтены как ошибочные")

    # Порядок меток - как в JTL, а не по алфавиту: он совпадает с порядком
    # шагов сценария, и заказчик читает отчёт именно в этом порядке.
    grouped = defaultdict(list)
    for row in jtl_data:
        grouped[row['label']].append(row)

    stats = [dict(collect_stats(rows), label=label) for label, rows in grouped.items()]
    total_stats = collect_stats(jtl_data)

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

    # min/max, а не первая и последняя строка файла: JMeter пишет строки
    # в порядке ЗАВЕРШЕНИЯ замеров, поэтому при нескольких потоках последняя
    # строка почти никогда не является самой поздней по времени.
    all_starts = [to_int(r.get('timeStamp')) for r in jtl_data]
    all_ends = [to_int(r.get('timeStamp')) + to_int(r.get('elapsed')) for r in jtl_data]
    first_ts, last_ts = min(all_starts), max(all_ends)

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
        (4, 'Всего выборок', len(jtl_data), f'Окончание тестирования ({tz_label})', end_time),
        (5, 'Ошибок', sum(1 for r in jtl_data
                          if str(r.get('success', '')).strip().upper() != 'TRUE'),
         'Длительность', duration_str),
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
    ws3 = wb.create_sheet('Исходные данные')
    raw_headers = list(jtl_data[0].keys())
    for col, header in enumerate(raw_headers, 1):
        cell = ws3.cell(row=1, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill_blue
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')

    numeric_columns = {'timeStamp', 'elapsed', 'bytes', 'sentBytes', 'grpThreads',
                       'allThreads', 'Latency', 'IdleTime', 'Connect'}
    raw_limit = EXCEL_MAX_ROWS - 1
    truncated = len(jtl_data) - raw_limit

    for r_idx, row in enumerate(jtl_data[:raw_limit], start=2):
        for col, header in enumerate(raw_headers, 1):
            value = row.get(header, '')
            # Числа записываются числами, иначе Excel показывает их как текст
            # и по ним нельзя ни отсортировать, ни построить формулу.
            if header in numeric_columns and str(value).strip().lstrip('-').isdigit():
                value = int(value)
            cell = ws3.cell(row=r_idx, column=col, value=value)
            cell.border = thin_border

    if truncated > 0:
        warnings.append(f"лист 'Исходные данные' обрезан: {truncated} строк "
                        f"не поместились в лимит Excel ({EXCEL_MAX_ROWS} строк)")

    if warnings_after:
        warnings.append(warnings_after)

    try:
        wb.save(output_file)
    except OSError as exc:
        raise ReportError(f"Не удалось сохранить '{output_file}': {exc}")

    return {
        'output': output_file,
        'sheets': list(wb.sheetnames),
        'rows': len(jtl_data),
        'steps': len(main_steps),
        'labels': len(stats),
        'errors': sum(1 for r in jtl_data
                      if str(r.get('success', '')).strip().upper() != 'TRUE'),
        'timezone': tz_label,
        'start': start_time,
        'end': end_time,
        'duration': duration_str,
        'verification': check,
        'warnings': warnings,
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
    """Разбор командной строки. Возвращает словарь параметров."""
    options = {'--tz': None, '--steps': None, '--standard': None, '--dashboard': None,
               '--config': None}
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ('-h', '--help'):
            print(USAGE)
            sys.exit(0)
        name, eq, inline = arg.partition('=')
        if name in VALUE_OPTIONS:
            if eq:
                options[name] = inline
                i += 1
            elif i + 1 < len(argv):
                options[name] = argv[i + 1]
                i += 2
            else:
                sys.exit(f"Ошибка: у {name} не указано значение.\n\n" + USAGE)
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
        sys.exit(USAGE)

    # report.toml (рядом с запуском или из --config) задает значения по умолчанию.
    import config
    try:
        cfg = config.load_for(options['--config'], os.getcwd())
    except ReportError as exc:
        sys.exit(str(exc))
    if cfg:
        options['--tz'] = options['--tz'] or cfg.timezone
        options['--steps'] = options['--steps'] or cfg.steps
    options['--steps'] = options['--steps'] or DEFAULT_STEP_PATTERN

    for path in (jtl_file, options['--standard'], options['--dashboard']):
        if path and not os.path.isfile(path):
            sys.exit(f"Файл не найден: '{path}'")

    try:
        tz = resolve_timezone(options['--tz'])
    except ReportError as exc:
        sys.exit(str(exc))
    return {'jtl': jtl_file, 'output': output_file, 'tz': tz,
            'steps': options['--steps'], 'standard': options['--standard'],
            'dashboard': options['--dashboard']}


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        info = create_excel_report(
            args['jtl'], args['output'], tz=args['tz'], step_pattern=args['steps'],
            standard_xml=args['standard'], dashboard_xml=args['dashboard'])
    except ReportError as exc:
        sys.exit(str(exc))
    for warning in info['warnings']:
        print(f"Внимание: {warning}", file=sys.stderr)
    print(f"Файл '{info['output']}' успешно создан!")
    print(f"   Листы: {', '.join(info['sheets'])}")
    print(f"   Строк данных: {info['rows']}")
    print(f"   Время в отчёте: {info['timezone']}")
    if info['verification']:
        v = info['verification']
        print(f"   Сверка с XML: {'расхождений нет' if v['ok'] else str(v['mismatches']) + ' расхождений'}"
              f" (проверено {v['checked']})")


if __name__ == '__main__':
    main()
