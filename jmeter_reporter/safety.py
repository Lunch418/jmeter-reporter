"""Spreadsheet formula injection guards (labels and responses come from the system under test)."""

FORMULA_TRIGGERS = ('=', '+', '-', '@', '\t', '\r')


def csv_safe(value):
    """Для CSV: строка, начинающаяся с = + - @, в Excel стала бы формулой."""
    if isinstance(value, str) and value.startswith(FORMULA_TRIGGERS):
        return "'" + value
    return value


def neutralize_formulas(ws):
    """Ячейки, которые openpyxl принял за формулы (метка '=HYPERLINK(...)'), делает текстом."""
    for row in ws.iter_rows():
        for cell in row:
            if cell.data_type == 'f':
                cell.data_type = 's'


def printable(text):
    """Text for a terminal or a CI log: control characters (ESC, CR, ...) become '?'.

    A label like '01. x\\x1b[1A\\x1b[2KPASS' could otherwise erase a FAIL line in the log.
    """
    return ''.join(ch if ch.isprintable() else '?' for ch in str(text))
