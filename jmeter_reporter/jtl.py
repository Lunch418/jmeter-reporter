"""Reading JMeter JTL (CSV): strict, streaming, no silent zeros."""
import csv
import os
import re

from .errors import ReportError


_INT = re.compile(r'\s*(-?[0-9]{1,18})\s*', re.ASCII)
_UINT = re.compile(r'\s*([0-9]{1,18})\s*', re.ASCII)


def is_int(value):
    """True for an ASCII decimal integer of up to 18 digits (the one definition of 'a number')."""
    return _INT.fullmatch(str(value)) is not None


def to_int(value, default=0):
    """int() устойчивый к пустым и нечисловым ячейкам (используется для необязательных
    колонок вроде bytes). Обязательные timeStamp/elapsed проверяет _checked: ошибка, не ноль.

    Только ASCII-цифры и до 18 знаков: '²', '--5' и число из 5000 цифр дают default,
    а не исключение.
    """
    match = _INT.fullmatch(str(value)) if value is not None else None
    return int(match.group(1)) if match else default


# Кодировка JTL. JMeter пишет UTF-8; JTL с Windows-агента бывает в cp1251:
# JTL_ENCODING=cp1251 python convert.py ...  Молчаливой подмены символов нет.
JTL_ENCODING = os.environ.get('JTL_ENCODING', 'utf-8-sig')
MAX_FIELD = 2 ** 24  # 16 MB: one unclosed quote must not swallow the whole file in memory
MAX_COLUMNS = 16384  # Excel's column limit
NUMERIC_REQUIRED = ('timeStamp', 'elapsed')
def iter_jtl_rows(jtl_file, limit=None, warnings=None):
    """Построчное чтение JTL (CSV): память не растет с размером файла.

    Битые данные не превращаются в нули: нечисловой timeStamp/elapsed или строка
    с неверным числом полей - ReportError с номером строки. Исключение одно:
    оборванная последняя строка (JMeter убили посреди записи) пропускается
    с предупреждением в warnings.
    """
    try:
        yield from _read_rows(jtl_file, limit, warnings)
    except FileNotFoundError:
        raise ReportError(f"Файл не найден: '{jtl_file}'")
    except OSError as exc:
        raise ReportError(f"Не удалось прочитать '{jtl_file}': {exc.strerror or exc}")
    except csv.Error as exc:
        raise ReportError(f"Файл '{jtl_file}' не разбирается как CSV: {exc}")
    except UnicodeDecodeError as exc:
        raise ReportError(
            f"Файл '{jtl_file}' не читается как {JTL_ENCODING} (байт {exc.start}).\n"
            f"Если JTL записан в другой кодировке, укажите ее: "
            f"JTL_ENCODING=cp1251 python convert.py ...")


def _read_rows(jtl_file, limit, warnings):
    # По умолчанию csv отвергает поле больше 128 КБ, а тело ответа в JTL бывает больше.
    csv.field_size_limit(MAX_FIELD)
    with open(jtl_file, 'r', encoding=JTL_ENCODING, newline='') as f:
        head = f.read(200)
        f.seek(0)
        if head.lstrip().startswith('<'):
            raise ReportError(
                f"Файл '{jtl_file}' похож на JTL в формате XML, а скрипт читает CSV.\n"
                f"В JMeter выставьте jmeter.save.saveservice.output_format=csv "
                f"и перезапустите тест."
            )
        reader = csv.DictReader(f)
        if len(reader.fieldnames or ()) > MAX_COLUMNS:
            raise ReportError(f"В '{jtl_file}' больше {MAX_COLUMNS} колонок: это не JTL.")
        pending = None
        for index, row in enumerate(reader):
            if pending is not None:
                yield _checked(pending, jtl_file)
            if limit is not None and index >= limit:
                return
            pending = (reader.line_num, row)
        if pending is not None:
            line, row = pending
            if None in row or None in row.values():
                if warnings is not None:
                    warnings.append(f"последняя строка JTL (№{line}) оборвана и пропущена")
                return
            yield _checked(pending, jtl_file)


def _checked(pending, jtl_file):
    line, row = pending
    if None in row or None in row.values():
        raise ReportError(f"{jtl_file}, строка {line}: неверное число полей в строке JTL.")
    for field in NUMERIC_REQUIRED:
        if field in row and not _UINT.fullmatch(row[field] or ''):
            hint = ''
            if field == 'timeStamp':
                hint = ("\nВероятно, jmeter.save.saveservice.timestamp_format задан не как ms: "
                        "выставьте timestamp_format=ms (по умолчанию) и перезапустите тест.")
            raise ReportError(
                f"{jtl_file}, строка {line}: в колонке {field} не целое неотрицательное число: "
                f"'{row[field][:40]}'.{hint}")
    return row


def parse_jtl_file(jtl_file, limit=None, warnings=None):
    """Читает JTL (CSV) в список словарей. limit - максимум строк (для предпросмотра)."""
    return list(iter_jtl_rows(jtl_file, limit, warnings))
