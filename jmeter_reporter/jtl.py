"""Reading JMeter JTL (CSV): strict, streaming, no silent zeros."""
import csv
import os
import re

from .errors import ReportError


def to_int(value, default=0):
    """int() устойчивый к пустым и нечисловым ячейкам JTL.

    dict.get(key, 0) здесь не спасает: в JTL колонка часто присутствует,
    но пустая, и .get вернёт '' - int('') падает с ValueError.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


# Кодировка JTL. JMeter пишет UTF-8; JTL с Windows-агента бывает в cp1251:
# JTL_ENCODING=cp1251 python convert.py ...  Молчаливой подмены символов нет.
JTL_ENCODING = os.environ.get('JTL_ENCODING', 'utf-8-sig')
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
        if field in row and not re.fullmatch(r'\s*-?\d+\s*', row[field] or ''):
            hint = ''
            if field == 'timeStamp':
                hint = ("\nВероятно, jmeter.save.saveservice.timestamp_format задан не как ms: "
                        "выставьте timestamp_format=ms (по умолчанию) и перезапустите тест.")
            raise ReportError(
                f"{jtl_file}, строка {line}: в колонке {field} не целое число: "
                f"'{row[field]}'.{hint}")
    return row


def parse_jtl_file(jtl_file, limit=None, warnings=None):
    """Читает JTL (CSV) в список словарей. limit - максимум строк (для предпросмотра)."""
    return list(iter_jtl_rows(jtl_file, limit, warnings))
