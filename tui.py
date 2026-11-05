#!/usr/bin/env python3
"""Terminal UI for the JMeter -> Excel report converter.

    python3 tui.py              # start in the current directory
    python3 tui.py /path/to/dir # start in a given directory

Keys: Ctrl+R - build the report, Ctrl+Q - quit, Tab / Shift+Tab - move between fields.
"""
import sys
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (Button, DirectoryTree, Footer, Header, Input, Label,
                             RichLog, Select)

import convert

# Input file types for the file browser: label -> extensions (None = everything).
FILE_TYPES = {
    'jtl': ('JTL / CSV (.jtl, .csv)', {'.jtl', '.csv'}),
    'all': ('Все файлы', None),
}

TIMEZONES = [
    ('Локальный (как на этой машине)', 'local'),
    ('UTC', 'UTC'),
    ('Москва (Europe/Moscow)', 'Europe/Moscow'),
    ('Екатеринбург (Asia/Yekaterinburg)', 'Asia/Yekaterinburg'),
    ('Новосибирск (Asia/Novosibirsk)', 'Asia/Novosibirsk'),
    ('Владивосток (Asia/Vladivostok)', 'Asia/Vladivostok'),
]


def default_output_path(jtl_path):
    """Рядом с входным файлом: results.jtl -> results_report.xlsx."""
    jtl_path = Path(jtl_path)
    return jtl_path.with_name(f'{jtl_path.stem}_report.xlsx')


class FileTree(DirectoryTree):
    """Дерево каталогов: скрытые файлы не показываем, файлы фильтруем по типу."""

    extensions = FILE_TYPES['jtl'][1]

    def filter_paths(self, paths):
        result = []
        for path in paths:
            if path.name.startswith('.'):
                continue
            if path.is_dir() or self.extensions is None \
                    or path.suffix.lower() in self.extensions:
                result.append(path)
        return result


class ReportApp(App):
    TITLE = 'JMeter -> Excel'
    SUB_TITLE = 'отчёт по нагрузочному тестированию'
    BINDINGS = [
        ('ctrl+r', 'build', 'Создать отчёт'),
        ('ctrl+q', 'quit', 'Выход'),
    ]
    CSS = """
    #tree-pane { width: 45%; border: round $primary; }
    #form-pane { width: 55%; padding: 0 1; }
    #tree-title, .label { color: $text-muted; margin-top: 1; }
    FileTree { height: 1fr; }
    #log { height: 1fr; min-height: 8; border: round $secondary; margin-top: 1; }
    #buttons { height: 3; margin-top: 1; }
    Button { margin-right: 2; }
    """

    def __init__(self, start_dir='.'):
        super().__init__()
        self.start_dir = Path(start_dir).expanduser().resolve()
        self._output_touched = False  # пользователь правил путь вручную

    # ------------------------------------------------------------ layout ----

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id='tree-pane'):
                yield Label('Тип файлов', id='tree-title')
                yield Select([(label, key) for key, (label, _) in FILE_TYPES.items()],
                             value='jtl', allow_blank=False, id='file-type')
                yield FileTree(self.start_dir, id='tree')
            with VerticalScroll(id='form-pane'):
                yield Label('Входной файл JTL (выберите в дереве или впишите путь)',
                            classes='label')
                yield Input(placeholder='path/to/jmeter.jtl', id='jtl')
                yield Label('Выходной файл Excel', classes='label')
                yield Input(placeholder='report.xlsx', id='output')
                yield Label('Часовой пояс', classes='label')
                yield Select(TIMEZONES, value='local', allow_blank=False, id='tz')
                yield Label('Свой пояс (необязательно: Europe/Samara, +05:00)',
                            classes='label')
                yield Input(placeholder='оставьте пустым, чтобы использовать список', id='tz-custom')
                yield Label('Шаги для графика (регулярное выражение)', classes='label')
                yield Input(value=convert.DEFAULT_STEP_PATTERN, id='steps')
                with Horizontal(id='buttons'):
                    yield Button('Создать отчёт', variant='success', id='build')
                    yield Button('Выход', id='quit')
                yield RichLog(id='log', wrap=True, markup=True)
        yield Footer()

    def on_mount(self):
        self.log_line(f'Каталог: {self.start_dir}')
        self.log_line('Выберите .jtl в дереве слева и нажмите Ctrl+R.')

    # ------------------------------------------------------------ events ----

    @on(Select.Changed, '#file-type')
    def _filter_changed(self, event):
        if event.value is Select.BLANK:
            return
        tree = self.query_one(FileTree)
        tree.extensions = FILE_TYPES[event.value][1]
        tree.reload()

    @on(DirectoryTree.FileSelected)
    def _file_selected(self, event):
        path = Path(event.path)
        self.query_one('#jtl', Input).value = str(path)
        if not self._output_touched:
            self.query_one('#output', Input).value = str(default_output_path(path))

    @on(Input.Changed, '#output')
    def _output_changed(self, event):
        # Автоподстановка тоже вызывает Changed, поэтому сравниваем с ожидаемым значением.
        jtl = self.query_one('#jtl', Input).value.strip()
        expected = str(default_output_path(jtl)) if jtl else ''
        self._output_touched = bool(event.value) and event.value != expected

    @on(Button.Pressed, '#build')
    def _build_pressed(self):
        self.action_build()

    @on(Button.Pressed, '#quit')
    def _quit_pressed(self):
        self.exit()

    # ----------------------------------------------------------- actions ----

    def log_line(self, text):
        self.query_one('#log', RichLog).write(text)

    def action_build(self):
        jtl = self.query_one('#jtl', Input).value.strip()
        output = self.query_one('#output', Input).value.strip()
        custom_tz = self.query_one('#tz-custom', Input).value.strip()
        tz_value = custom_tz or self.query_one('#tz', Select).value
        steps = self.query_one('#steps', Input).value.strip() or convert.DEFAULT_STEP_PATTERN

        if not jtl:
            self.log_line('[red]Не выбран входной файл.[/red]')
            return
        if not Path(jtl).expanduser().is_file():
            self.log_line(f'[red]Файл не найден: {jtl}[/red]')
            return
        if not output:
            output = str(default_output_path(jtl))
            self.query_one('#output', Input).value = output
        if not output.lower().endswith('.xlsx'):
            self.log_line('[red]Выходной файл должен иметь расширение .xlsx[/red]')
            return
        try:
            tz = convert.resolve_timezone(str(tz_value))
            self._run_build(str(Path(jtl).expanduser()), str(Path(output).expanduser()),
                            tz, steps)
        except convert.ReportError as exc:
            self.log_line(f'[red]{exc}[/red]')

    def _run_build(self, jtl, output, tz, steps):
        self.query_one('#build', Button).disabled = True
        self.log_line(f'Обработка {jtl} ...')
        self._build_worker(jtl, output, tz, steps)

    @work(thread=True, exclusive=True)
    def _build_worker(self, jtl, output, tz, steps):
        try:
            info = convert.create_excel_report(jtl, output, tz=tz, step_pattern=steps)
        except convert.ReportError as exc:
            self.call_from_thread(self._build_failed, str(exc))
        except Exception as exc:  # неожиданная ошибка не должна ронять интерфейс
            self.call_from_thread(self._build_failed, f'{type(exc).__name__}: {exc}')
        else:
            self.call_from_thread(self._build_done, info)

    def _build_failed(self, message):
        self.query_one('#build', Button).disabled = False
        self.log_line(f'[red]Ошибка: {message}[/red]')

    def _build_done(self, info):
        self.query_one('#build', Button).disabled = False
        self.log_line(f'[green]Готово: {info["output"]}[/green]')
        self.log_line(f'  Выборок: {info["rows"]}, меток: {info["labels"]}, '
                      f'шагов на графике: {info["steps"]}, ошибок: {info["errors"]}')
        self.log_line(f'  Начало: {info["start"]} ({info["timezone"]})')
        self.log_line(f'  Конец:  {info["end"]}')
        self.log_line(f'  Длительность: {info["duration"]}')
        for warning in info['warnings']:
            self.log_line(f'[yellow]Внимание: {warning}[/yellow]')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    start = argv[0] if argv else '.'
    if not Path(start).expanduser().is_dir():
        sys.exit(f"Каталог не найден: '{start}'")
    ReportApp(start).run()


if __name__ == '__main__':
    main()
