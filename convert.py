#!/usr/bin/env python3
import csv
import statistics
import os
import sys
from collections import defaultdict
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference

def parse_jtl_file(jtl_file):
    data = []
    with open(jtl_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data

def format_time(ms):
    """Преобразует миллисекунды в формат 'X мин Y,ZZZ сек'"""
    total_seconds = ms / 1000.0
    minutes = int(total_seconds) // 60
    seconds = total_seconds - (minutes * 60)
    return f"{minutes} мин {seconds:.3f}".replace('.', ',') + " сек"

def parse_timestamp(ts_ms):
    """Преобразует timestamp в читаемый формат"""
    try:
        dt = datetime.utcfromtimestamp(int(ts_ms) / 1000)
        return dt.strftime('%d.%m.%Y %H:%M:%S.%f')[:-3]
    except:
        return 'N/A'

def create_excel_report(jtl_file, dashboard_xml, standard_xml, output_file):
    # Парсим JTL файл
    jtl_data = parse_jtl_file(jtl_file)
    
    if not jtl_data:
        print("❌ Не удалось прочитать данные из JTL файла!")
        return

    # Группируем и считаем статистику
    grouped = defaultdict(list)
    for row in jtl_data:
        grouped[row['label']].append(row)
    
    stats = []
    for label, rows in grouped.items():
        elapsed = [int(r['elapsed']) for r in rows]
        errors = sum(1 for r in rows if r.get('success', '').upper() != 'TRUE')
        total_bytes = sum(int(r.get('bytes', 0)) for r in rows)
        total_sent = sum(int(r.get('sentBytes', 0)) for r in rows)
        
        timestamps = [int(r['timeStamp']) for r in rows]
        duration_sec = (max(timestamps) - min(timestamps)) / 1000.0 if len(timestamps) > 1 else 1.0
        
        # НЕ округляем - сохраняем полную точность!
        throughput = len(rows) / duration_sec if duration_sec > 0 else 0
        received_kb = total_bytes / 1024 / duration_sec if duration_sec > 0 else 0
        sent_kb = total_sent / 1024 / duration_sec if duration_sec > 0 else 0
        error_pct = errors / len(rows) * 100 if len(rows) > 0 else 0
        
        sorted_elapsed = sorted(elapsed)
        n = len(sorted_elapsed)
        
        # Правильная формула для перцентилей: round(n * p) - 1
        p90_idx = max(0, round(n * 0.90) - 1)
        p95_idx = max(0, round(n * 0.95) - 1)
        p99_idx = max(0, round(n * 0.99) - 1)
        
        stats.append({
            'label': label,
            'samples': n,
            'avg': round(statistics.mean(elapsed)),
            'median': round(statistics.median(elapsed)),
            'p90': sorted_elapsed[p90_idx],
            'p95': sorted_elapsed[p95_idx],
            'p99': sorted_elapsed[p99_idx],
            'min': min(elapsed),
            'max': max(elapsed),
            'error_pct': error_pct,  # Полная точность
            'throughput': throughput,  # Полная точность
            'received_kb': received_kb,  # Полная точность
            'sent_kb': sent_kb,  # Полная точность
        })

    # НЕ сортируем - сохраняем порядок из JTL файла
    stats_sorted = stats

    # Общая статистика
    all_elapsed = [int(r['elapsed']) for r in jtl_data]
    total_errors = sum(1 for r in jtl_data if r.get('success', '').upper() != 'TRUE')
    all_timestamps = [int(r['timeStamp']) for r in jtl_data]
    duration_ms = max(all_timestamps) - min(all_timestamps)
    
    start_time = parse_timestamp(all_timestamps[0])
    end_time = parse_timestamp(all_timestamps[-1])
    duration_str = format_time(duration_ms)

    # Создаем Excel файл
    wb = Workbook()
    
    # Стили - как в примере
    header_font_bold_11 = Font(bold=True, size=11)
    header_font_bold_16 = Font(bold=True, size=16)
    thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                         top=Side(style='thin'), bottom=Side(style='thin'))
    header_fill_blue = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')  # Темный синий
    header_font_white = Font(bold=True, size=11, color='FFFFFF')
    label_fill = PatternFill(start_color='DDEBF7', end_color='DDEBF7', fill_type='solid')  # Светло-голубой
    value_fill = PatternFill(start_color='FFFFFF', end_color='FFFFFF', fill_type='solid')  # Белый
    total_fill = PatternFill(start_color='E2F0D9', end_color='E2F0D9', fill_type='solid')  # Светло-зеленый

    # ================= ЛИСТ 1: СВОДКА =================
    ws1 = wb.active
    ws1.title = 'Сводка'
    
    # Заголовок (строка 1)
    ws1['A1'] = 'Отчет по результатам нагрузочного тестирования'
    ws1['A1'].font = header_font_bold_16
    ws1.merge_cells('A1:E1')
    
    # Пустая строка 2
    
    # Информация о тесте (строки 3-5)
    # Строка 3
    ws1['A3'] = 'Файл JTL'
    ws1['A3'].font = header_font_bold_11
    ws1['A3'].fill = label_fill
    ws1['B3'] = os.path.basename(jtl_file)
    ws1['B3'].font = header_font_bold_11
    ws1['B3'].fill = value_fill
    
    ws1['D3'] = 'Начало тестирования (UTC+5)'
    ws1['D3'].font = header_font_bold_11
    ws1['D3'].fill = label_fill
    ws1['E3'] = start_time
    ws1['E3'].font = header_font_bold_11
    ws1['E3'].fill = value_fill
    
    # Строка 4
    ws1['A4'] = 'Всего выборок'
    ws1['A4'].font = header_font_bold_11
    ws1['A4'].fill = label_fill
    ws1['B4'] = len(jtl_data)
    ws1['B4'].font = header_font_bold_11
    ws1['B4'].fill = value_fill
    
    ws1['D4'] = 'Окончание тестирования (UTC+5)'
    ws1['D4'].font = header_font_bold_11
    ws1['D4'].fill = label_fill
    ws1['E4'] = end_time
    ws1['E4'].font = header_font_bold_11
    ws1['E4'].fill = value_fill
    
    # Строка 5
    ws1['A5'] = 'Ошибок'
    ws1['A5'].font = header_font_bold_11
    ws1['A5'].fill = label_fill
    ws1['B5'] = total_errors
    ws1['B5'].font = header_font_bold_11
    ws1['B5'].fill = value_fill
    
    ws1['D5'] = 'Длительность'
    ws1['D5'].font = header_font_bold_11
    ws1['D5'].fill = label_fill
    ws1['E5'] = duration_str
    ws1['E5'].font = header_font_bold_11
    ws1['E5'].fill = value_fill
    
    # Пустая строка 6
    
    # Заголовки таблицы (строка 7)
    headers = ['Label', '# Samples', 'Average', 'Median', '90% Line', '95% Line', '99% Line', 'Min', 'Max', 'Error %', 'Throughput', 'Received KB/sec', 'Sent KB/sec']
    
    for col, header in enumerate(headers, 1):
        cell = ws1.cell(row=7, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill_blue
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # Данные (строка 8+)
    row_idx = 8
    for s in stats_sorted:
        values = [
            s['label'], s['samples'], s['avg'], s['median'],
            s['p90'], s['p95'], s['p99'],
            s['min'], s['max'], s['error_pct'],
            s['throughput'], s['received_kb'], s['sent_kb']
        ]
        for col, val in enumerate(values, 1):
            cell = ws1.cell(row=row_idx, column=col, value=val)
            cell.border = thin_border
            if col > 1:
                cell.alignment = Alignment(horizontal='right')
            else:
                cell.alignment = Alignment(horizontal='left')
            # Форматирование чисел с 3 знаками после запятой для колонок 10-13
            if col >= 10:
                cell.number_format = '0.000'
        row_idx += 1

    # Итоговая строка TOTAL (полная точность)
    total_duration_sec = duration_ms / 1000.0 if duration_ms > 0 else 1.0
    total_throughput = len(jtl_data) / total_duration_sec if total_duration_sec > 0 else 0
    total_received_kb = sum(int(r.get('bytes', 0)) for r in jtl_data) / 1024 / total_duration_sec if total_duration_sec > 0 else 0
    total_sent_kb = sum(int(r.get('sentBytes', 0)) for r in jtl_data) / 1024 / total_duration_sec if total_duration_sec > 0 else 0
    total_error_pct = total_errors / len(jtl_data) * 100 if len(jtl_data) > 0 else 0
    
    # Правильный расчет перцентилей для TOTAL
    sorted_all = sorted(all_elapsed)
    total_n = len(sorted_all)
    total_p90_idx = max(0, round(total_n * 0.90) - 1)
    total_p95_idx = max(0, round(total_n * 0.95) - 1)
    total_p99_idx = max(0, round(total_n * 0.99) - 1)
    
    total_values = [
        'TOTAL', len(jtl_data),
        round(statistics.mean(all_elapsed)),
        round(statistics.median(all_elapsed)),
        sorted_all[total_p90_idx],
        sorted_all[total_p95_idx],
        sorted_all[total_p99_idx],
        min(all_elapsed), max(all_elapsed),
        total_error_pct,  # Полная точность
        total_throughput,  # Полная точность
        total_received_kb,  # Полная точность
        total_sent_kb  # Полная точность
    ]
    
    for col, val in enumerate(total_values, 1):
        cell = ws1.cell(row=row_idx, column=col, value=val)
        cell.font = header_font_bold_11
        cell.fill = total_fill
        cell.border = thin_border
        if col > 1:
            cell.alignment = Alignment(horizontal='right')
        else:
            cell.alignment = Alignment(horizontal='left')
        # Форматирование для колонок 10-13
        if col >= 10:
            cell.number_format = '0.000'

    # Автоширина колонок
    col_widths = [30, 12, 12, 12, 12, 12, 12, 10, 10, 12, 15, 18, 15]
    for col, width in enumerate(col_widths, 1):
        ws1.column_dimensions[get_column_letter(col)].width = width

    # ================= ЛИСТ 2: ГРАФИК ВРЕМЕНИ =================
    ws2 = wb.create_sheet('График времени')
    ws2['A1'] = 'Агрегированный график времени выполнения шагов'
    ws2['A1'].font = header_font_bold_16
    ws2.merge_cells('A1:J1')
    
    # Пустая строка 2
    graph_headers = ['Label', '# Samples', 'Average', 'Median', '90% Line', '95% Line', '99% Line', 'Min', 'Max', 'Error %']
    for col, header in enumerate(graph_headers, 1):
        cell = ws2.cell(row=3, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill_blue
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
    
    # Только основные шаги (01. - 10.)
    main_steps = [s for s in stats_sorted if any(s['label'].startswith(f"{i:02d}.") for i in range(1, 11))]
    
    r_idx = 4
    for s in main_steps:
        values = [s['label'], s['samples'], s['avg'], s['median'], s['p90'], s['p95'], s['p99'], s['min'], s['max'], s['error_pct']]
        for col, val in enumerate(values, 1):
            cell = ws2.cell(row=r_idx, column=col, value=val)
            cell.border = thin_border
            if col > 1:
                cell.alignment = Alignment(horizontal='right')
            else:
                cell.alignment = Alignment(horizontal='left')
            # Форматирование для колонки Error %
            if col == 10:
                cell.number_format = '0.000'
        r_idx += 1
    
    # Добавляем горизонтальную диаграмму с Average и 90% Line
    chart1 = BarChart()
    chart1.type = "bar"  # Горизонтальная диаграмма
    chart1.style = 10
    chart1.title = "Время выполнения шагов (мс)"
    chart1.x_axis.title = 'Время, мс'
    chart1.y_axis.title = 'Шаги'
    
    # Average (колонка 3)
    data_avg = Reference(ws2, min_col=3, min_row=3, max_row=2+len(main_steps))
    # 90% Line (колонка 5)
    data_p90 = Reference(ws2, min_col=5, min_row=3, max_row=2+len(main_steps))
    # Категории (шаги)
    cats = Reference(ws2, min_col=1, min_row=4, max_row=3+len(main_steps))
    
    chart1.add_data(data_avg, titles_from_data=True)
    chart1.add_data(data_p90, titles_from_data=True)
    chart1.set_categories(cats)
    chart1.height = 12
    chart1.width = 20
    ws2.add_chart(chart1, "A" + str(r_idx + 2))
    
    for col in range(1, len(graph_headers) + 1):
        max_length = max(len(str(ws2.cell(row=r, column=col).value or '')) for r in range(1, r_idx))
        ws2.column_dimensions[get_column_letter(col)].width = min(max_length + 2, 30)

    # ================= ЛИСТ 3: ИСХОДНЫЕ ДАННЫЕ =================
    ws3 = wb.create_sheet('Исходные данные')
    raw_headers = list(jtl_data[0].keys())
    for col, header in enumerate(raw_headers, 1):
        cell = ws3.cell(row=1, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill_blue
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
    
    for r_idx, row in enumerate(jtl_data, start=2):
        for col, header in enumerate(raw_headers, 1):
            cell = ws3.cell(row=r_idx, column=col, value=row.get(header, ''))
            cell.border = thin_border

    wb.save(output_file)
    print(f" Файл '{output_file}' успешно создан!")
    print(f"   Листы: {', '.join(wb.sheetnames)}")
    print(f"   Строк данных: {len(jtl_data)}")

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print("Использование: python3 convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx")
        sys.exit(1)
    
    jtl_file = sys.argv[1]
    dashboard_xml = sys.argv[2]
    standard_xml = sys.argv[3]
    output_file = sys.argv[4]
    
    create_excel_report(jtl_file, dashboard_xml, standard_xml, output_file)