"""Streaming writer for the 'raw data' sheet.

openpyxl keeps every cell as a Python object (about 500 bytes each), so a 400 000-row JTL
needs several GB. The report is therefore built by openpyxl WITHOUT the data rows (header
and one styled placeholder row only), and the rows are then written straight into the
.xlsx archive as XML, one at a time. Memory does not depend on the number of rows.
The cell style is taken from openpyxl itself (same border as before), so the sheet looks
and reads exactly as it did.
"""
import os
import re
import zipfile
from xml.sax.saxutils import escape

import openpyxl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.utils import get_column_letter

from . import jtl
from .errors import ReportError

MAX_CELL_CHARS = 32767  # Excel limit


def _text_cell(ref, style, value, counter):
    text = ILLEGAL_CHARACTERS_RE.sub('', value)
    if len(text) > MAX_CELL_CHARS:
        counter[0] += 1
        text = text[:MAX_CELL_CHARS]
    return (f'<c r="{ref}" s="{style}" t="inlineStr"><is>'
            f'<t xml:space="preserve">{escape(text)}</t></is></c>')


def _number_cell(ref, style, value):
    return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'


def row_xml(number, values, style, letters, counter=None):
    counter = counter if counter is not None else [0]
    cells = []
    for letter, value in zip(letters, values):
        ref = f'{letter}{number}'
        if value == '':  # empty cell keeps its border, like openpyxl does
            cells.append(f'<c r="{ref}" s="{style}"/>')
        elif isinstance(value, int) and not isinstance(value, bool):
            cells.append(_number_cell(ref, style, value))
        else:
            cells.append(_text_cell(ref, style, str(value), counter))
    return f'<row r="{number}">{"".join(cells)}</row>'


def fill_sheet(src, dst, sheet_index, rows, style, numeric_columns, headers, total_rows):
    """Copy the workbook `src` to `dst`, filling sheet number `sheet_index` (1-based).

    `rows` yields dicts (one per JTL line); `total_rows` is how many of them to write
    (known in advance from the statistics pass, it also gives the sheet dimension).
    Returns (rows written, cells cut to Excel's 32 767-character limit).
    Raises ReportError when the sheet XML written by this openpyxl version has an unexpected
    shape (this code relies on it; CI checks the oldest supported openpyxl too).
    """
    target = f'xl/worksheets/sheet{sheet_index}.xml'
    letters = [get_column_letter(i) for i in range(1, len(headers) + 1)]
    last_ref = f'{letters[-1]}{total_rows + 1}'
    written = 0
    cut = [0]
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename != target:
                zout.writestr(item, zin.read(item.filename))
                continue
            xml = zin.read(item.filename).decode('utf-8')
            head, found, rest = xml.partition('<sheetData>')
            body, found_end, tail = rest.partition('</sheetData>')
            header = re.search(r'<row r="1".*?</row>', body, re.S) if found and found_end else None
            if header is None:
                raise ReportError(
                    f"Несовместимая версия openpyxl {openpyxl.__version__}: не найден заголовок "
                    f"листа в {target}. Используйте openpyxl от 3.0.10 до 3.1.x "
                    f"или отключите лист: --no-raw-data.")
            header_row = header.group(0)
            head = re.sub(r'<dimension ref="[^"]*"', f'<dimension ref="A1:{last_ref}"', head)
            info = zipfile.ZipInfo(target, item.date_time)
            info.compress_type = zipfile.ZIP_DEFLATED  # ZipInfo defaults to STORED
            with zout.open(info, 'w', force_zip64=True) as out:
                out.write((head + '<sheetData>' + header_row).encode('utf-8'))
                chunk = []
                for row in rows:
                    if written >= total_rows:
                        break
                    values = []
                    for header in headers:
                        value = row.get(header, '')
                        if header in numeric_columns and jtl.is_int(value):
                            value = jtl.to_int(value)
                        values.append(value)
                    chunk.append(row_xml(written + 2, values, style, letters, cut))
                    written += 1
                    if len(chunk) >= 500:
                        out.write(''.join(chunk).encode('utf-8'))
                        chunk = []
                out.write((''.join(chunk) + '</sheetData>' + tail).encode('utf-8'))
    return written, cut[0]


def atomic_replace(tmp, final):
    """Move a finished file over the target in one step: a failed build never destroys
    the previous report."""
    os.replace(tmp, final)
