"""A small TOML parser on the standard library only.

Used by config.py when neither the stdlib `tomllib` (Python 3.11+) nor the `tomli` package
is available, e.g. on an isolated machine where nothing can be installed. It understands
what report.toml needs:

    comments, [tables], [dotted.tables], [[arrays.of.tables]], key = value, dotted keys,
    "basic" and 'literal' strings, integers, floats, booleans, arrays (also multi-line),
    inline tables.

Not supported (raises TOMLDecodeError, never guesses): multi-line strings, dates and times,
hex/octal/binary numbers, inf/nan. Same API as tomllib: load(binary_file), loads(str).
"""
import re

__all__ = ['TOMLDecodeError', 'load', 'loads']


class TOMLDecodeError(ValueError):
    pass


_BARE_KEY = re.compile(r'[A-Za-z0-9_-]+')
_INT = re.compile(r'[+-]?(0|[1-9](_?[0-9])*)')
_FLOAT = re.compile(r'[+-]?(0|[1-9](_?[0-9])*)(\.[0-9](_?[0-9])*)?([eE][+-]?[0-9](_?[0-9])*)?')
_ESCAPES = {'b': '\b', 't': '\t', 'n': '\n', 'f': '\f', 'r': '\r', '"': '"', '\\': '\\'}


def load(fp):
    return loads(fp.read().decode('utf-8'))


def loads(text):
    return _Parser(text.lstrip('\ufeff')).parse()


class _Parser:
    def __init__(self, text):
        self.s = text
        self.i = 0

    # ---------------------------------------------------------------- utils ----

    def error(self, message):
        line = self.s.count('\n', 0, self.i) + 1
        raise TOMLDecodeError(f'{message} (строка {line})')

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ''

    def skip_spaces(self):
        while self.peek() in (' ', '\t'):
            self.i += 1

    def skip_comment(self):
        if self.peek() == '#':
            while self.peek() not in ('\n', ''):
                self.i += 1

    def skip_blank(self):
        """Whitespace, newlines and comments (between statements and inside arrays)."""
        while True:
            c = self.peek()
            if c in (' ', '\t', '\r', '\n'):
                self.i += 1
            elif c == '#':
                self.skip_comment()
            else:
                return

    def end_of_line(self):
        self.skip_spaces()
        self.skip_comment()
        if self.peek() == '\r':
            self.i += 1
        if self.peek() not in ('\n', ''):
            self.error('ожидался конец строки')

    # ------------------------------------------------------------------ keys ----

    def key(self):
        self.skip_spaces()
        c = self.peek()
        if c == '"':
            return self.basic_string()
        if c == "'":
            return self.literal_string()
        m = _BARE_KEY.match(self.s, self.i)
        if not m:
            self.error('ожидался ключ')
        self.i = m.end()
        return m.group(0)

    def key_path(self):
        path = [self.key()]
        while True:
            self.skip_spaces()
            if self.peek() != '.':
                return path
            self.i += 1
            path.append(self.key())

    # --------------------------------------------------------------- strings ----

    def basic_string(self):
        if self.s.startswith('"""', self.i):
            self.error('многострочные строки не поддерживаются')
        self.i += 1
        out = []
        while True:
            c = self.peek()
            if c in ('', '\n'):
                self.error('строка не закрыта')
            self.i += 1
            if c == '"':
                return ''.join(out)
            if c == '\\':
                e = self.peek()
                self.i += 1
                if e in _ESCAPES:
                    out.append(_ESCAPES[e])
                elif e in ('u', 'U'):
                    size = 4 if e == 'u' else 8
                    digits = self.s[self.i:self.i + size]
                    if len(digits) != size or not re.fullmatch(r'[0-9A-Fa-f]+', digits):
                        self.error('некорректная escape-последовательность')
                    self.i += size
                    out.append(chr(int(digits, 16)))
                else:
                    self.error('неизвестная escape-последовательность')
            else:
                out.append(c)

    def literal_string(self):
        if self.s.startswith("'''", self.i):
            self.error('многострочные строки не поддерживаются')
        end = self.s.find("'", self.i + 1)
        newline = self.s.find('\n', self.i + 1)
        if end == -1 or (newline != -1 and newline < end):
            self.error('строка не закрыта')
        value = self.s[self.i + 1:end]
        self.i = end + 1
        return value

    # ---------------------------------------------------------------- values ----

    def value(self):
        self.skip_spaces()
        c = self.peek()
        if c == '"':
            return self.basic_string()
        if c == "'":
            return self.literal_string()
        if c == '[':
            return self.array()
        if c == '{':
            return self.inline_table()
        for word, result in (('true', True), ('false', False)):
            if self.s.startswith(word, self.i):
                self.i += len(word)
                return result
        return self.number()

    def number(self):
        start = self.i
        while self.peek() not in ('', ',', ']', '}', ' ', '\t', '\r', '\n', '#'):
            self.i += 1
        token = self.s[start:self.i]
        if not token:
            self.error('ожидалось значение')
        if _INT.fullmatch(token):
            return int(token.replace('_', ''))
        if _FLOAT.fullmatch(token):
            return float(token.replace('_', ''))
        self.i = start
        self.error(f"неподдерживаемое значение '{token}'")

    def array(self):
        self.i += 1
        items = []
        while True:
            self.skip_blank()
            if self.peek() == ']':
                self.i += 1
                return items
            items.append(self.value())
            self.skip_blank()
            if self.peek() == ',':
                self.i += 1
            elif self.peek() != ']':
                self.error("в массиве ожидалась ',' или ']'")

    def inline_table(self):
        self.i += 1
        table = {}
        self.skip_spaces()
        if self.peek() == '}':
            self.i += 1
            return table
        while True:
            path = self.key_path()
            self.skip_spaces()
            if self.peek() != '=':
                self.error("ожидался '='")
            self.i += 1
            self.assign(table, path, self.value())
            self.skip_spaces()
            c = self.peek()
            self.i += 1
            if c == '}':
                return table
            if c != ',':
                self.i -= 1
                self.error("в таблице ожидалась ',' или '}'")

    # ------------------------------------------------------------ structure ----

    def assign(self, table, path, value):
        for part in path[:-1]:
            nxt = table.setdefault(part, {})
            if not isinstance(nxt, dict):
                self.error(f"ключ '{part}' уже занят")
            table = nxt
        if path[-1] in table:
            self.error(f"ключ '{path[-1]}' повторяется")
        table[path[-1]] = value

    def descend(self, root, path):
        """Table for a header path; the last element of an array of tables if one is met."""
        table = root
        for part in path:
            nxt = table.setdefault(part, {})
            if isinstance(nxt, list):
                if not nxt or not isinstance(nxt[-1], dict):
                    self.error(f"'{part}' не таблица")
                nxt = nxt[-1]
            if not isinstance(nxt, dict):
                self.error(f"'{part}' не таблица")
            table = nxt
        return table

    def parse(self):
        root = {}
        current = root
        seen_tables = set()
        while True:
            self.skip_blank()
            if self.i >= len(self.s):
                return root
            if self.peek() == '[':
                array = self.s.startswith('[[', self.i)
                self.i += 2 if array else 1
                path = self.key_path()
                self.skip_spaces()
                closing = ']]' if array else ']'
                if not self.s.startswith(closing, self.i):
                    self.error(f"ожидалось '{closing}'")
                self.i += len(closing)
                self.end_of_line()
                parent = self.descend(root, path[:-1])
                if array:
                    items = parent.setdefault(path[-1], [])
                    if not isinstance(items, list):
                        self.error(f"'{path[-1]}' уже не массив таблиц")
                    current = {}
                    items.append(current)
                else:
                    ident = tuple(path)
                    if ident in seen_tables:
                        self.error(f"таблица [{'.'.join(path)}] повторяется")
                    seen_tables.add(ident)
                    current = parent.setdefault(path[-1], {})
                    if not isinstance(current, dict):
                        self.error(f"'{path[-1]}' не таблица")
            else:
                path = self.key_path()
                self.skip_spaces()
                if self.peek() != '=':
                    self.error("ожидался '='")
                self.i += 1
                self.assign(current, path, self.value())
                self.end_of_line()
