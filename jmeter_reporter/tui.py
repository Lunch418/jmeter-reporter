#!/usr/bin/env python3
"""Terminal UI for the JMeter -> Excel report converter.

    python3 tui.py              # start in the current directory
    python3 tui.py /path/to/dir # start in a given directory

Keys: Ctrl+R build, Ctrl+O files, Ctrl+U folder up, Ctrl+B open folder,
Ctrl+F file type, Tab next field, Ctrl+Q quit.
"""
import os
import sys
from pathlib import Path

try:
    from rich.text import Text
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.theme import Theme
    from textual.widgets import DirectoryTree, Input, RichLog, Select, Static
except ImportError as _exc:  # the interface is optional: the CLI works without it
    if __name__ == '__main__':
        sys.exit("Для интерфейса нужен пакет textual: pip install -r requirements-tui.txt\n"
                 "Без него работают convert.py и cli.py (консольный режим).")
    raise

from . import compare
from . import config
from . import convert
from . import history
from . import preview
from . import workflow
from .errors import ReportError
from .stats import DEFAULT_STEP_PATTERN
from .timeutil import resolve_timezone

ACCENT = '#d97757'   # the orange of Claude Code
DIM = '#8b8b8b'
LINE = '#3d3a37'
OK = '#6fbf73'
WARN = '#e5c07b'
ERR = '#e06c75'

THEME = Theme(
    name='claude-report',
    primary=ACCENT,
    secondary=ACCENT,
    accent=ACCENT,
    background='#1b1a19',
    surface='#232120',
    panel='#232120',
    foreground='#e6e1da',
    dark=True,
)

# File types shown in the browser: key -> (label, extensions or None for everything).
FILE_TYPES = {
    'jmeter': ('.jtl .csv .xml', {'.jtl', '.csv', '.xml'}),
    'all': ('все файлы', None),
}
PREVIEWABLE = {'.jtl', '.csv', '.xml'}

# Extra outputs next to the Excel report: label -> (select value, formats or None = from config).
EXPORT_CHOICES = [
    ('как в конфиге', 'config'),
    ('только Excel', 'none'),
    ('+ HTML', 'html'),
    ('+ CSV', 'csv'),
    ('+ HTML и CSV', 'both'),
]
EXPORT_FORMATS_BY_CHOICE = {'config': None, 'none': [], 'html': ['html'], 'csv': ['csv'],
                            'both': ['html', 'csv']}

TIMEZONES = [
    ('локальный', 'local'),
    ('UTC', 'UTC'),
    ('Москва', 'Europe/Moscow'),
    ('Екатеринбург', 'Asia/Yekaterinburg'),
    ('Новосибирск', 'Asia/Novosibirsk'),
    ('Владивосток', 'Asia/Vladivostok'),
]


SAMPLES_DIR = Path(__file__).resolve().parent / 'samples'
REPORTS_DIR_NAME = 'reports'


def default_output_path(jtl_path):
    """Where the report goes by default.

    Next to the input (results.jtl -> results_report.xlsx), except two cases where
    that would be a bad place: the bundled demo data (it would litter the project)
    and a folder we cannot write to (e.g. a read-only mount). Those go to
    ./reports/ in the current directory.
    """
    jtl_path = Path(jtl_path)
    name = f'{jtl_path.stem}_report.xlsx'
    folder = jtl_path.parent
    try:
        is_demo = folder.resolve() == SAMPLES_DIR
    except OSError:
        is_demo = False
    if is_demo or not (folder.is_dir() and os.access(folder, os.W_OK)):
        return Path.cwd() / REPORTS_DIR_NAME / name
    return folder / name


def classify_xml(path):
    """'dashboard' or 'standard' by file name (dashBoard_jmeter.xml / standardResults.xml)."""
    return 'dashboard' if 'dash' in Path(path).name.lower() else 'standard'


def find_xml_artifacts(jtl_path):
    """Look for the two Jenkins XML files next to the JTL. Returns (standard, dashboard)."""
    folder = Path(jtl_path).parent
    standard = dashboard = ''
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return standard, dashboard
    for entry in entries:
        name = entry.name.lower()
        if not entry.is_file() or not name.endswith('.xml'):
            continue
        if name.startswith('standardresults') and not standard:
            standard = str(entry)
        elif name.startswith('dashboard') and not dashboard:
            dashboard = str(entry)
    return standard, dashboard


def short_path(path):
    """/home/user/x -> ~/x for display."""
    home = str(Path.home())
    text = str(path)
    return '~' + text[len(home):] if text.startswith(home) else text


CLUTTER_DIRS = {'__pycache__', 'node_modules', 'venv', 'site-packages', '.venv'}


def is_clutter(path):
    """Service folders nobody wants to browse: caches, virtualenvs, packaging leftovers."""
    name = path.name
    return name in CLUTTER_DIRS or name.endswith('.egg-info')


class FileTree(DirectoryTree):
    """Directory tree: hidden files are skipped, files are filtered by type."""

    # Plain ASCII markers instead of the emoji icons Textual uses by default.
    ICON_NODE = '+ '
    ICON_NODE_EXPANDED = '- '
    ICON_FILE = '  '

    extensions = FILE_TYPES['jmeter'][1]
    show_root = False  # the opened folder is in the 'папка' field; list its contents directly

    BINDINGS = [Binding('backspace', 'app.folder_up', 'выше', show=False)]

    def filter_paths(self, paths):
        result = []
        for path in paths:
            if path.name.startswith('.') or is_clutter(path):
                continue
            if path.is_dir() or self.extensions is None \
                    or path.suffix.lower() in self.extensions:
                result.append(path)
        return result


class ReportApp(App):
    TITLE = 'JMeter -> Excel'
    # priority=True: the keys work from any field. Without it a focused Input swallows
    # Ctrl+U (clears the line), Ctrl+E / Ctrl+F / Ctrl+B (move the cursor).
    BINDINGS = [
        Binding('ctrl+r', 'build', 'создать', priority=True),
        Binding('ctrl+o', 'focus_files', 'файлы', priority=True),
        Binding('ctrl+u', 'folder_up', 'папка выше', priority=True),
        Binding('ctrl+b', 'open_folder', 'открыть папку', priority=True),
        Binding('ctrl+f', 'toggle_filter', 'тип файлов', priority=True),
        Binding('ctrl+e', 'set_baseline', 'эталон', priority=True),
        Binding('ctrl+j', 'show_history', 'история', priority=True),
        Binding('ctrl+q', 'quit', 'выход', priority=True),
    ]
    CSS = f"""
    Screen {{ background: $background; padding: 0 1; }}

    #header {{ height: 1; margin-top: 1; }}
    #prompt {{ border: round {LINE}; height: 3; }}
    #prompt:focus-within {{ border: round {ACCENT}; }}
    #prompt-mark {{ width: 3; color: {ACCENT}; text-style: bold; padding-left: 1; }}

    #columns {{ height: 1fr; }}
    #left {{ width: 45%; min-width: 58; }}
    #right {{ width: 1fr; margin-left: 1; }}

    .panel {{ border: round {LINE}; border-title-color: {DIM}; border-title-align: left;
              padding: 0 1; }}
    .panel:focus-within {{ border: round {ACCENT}; border-title-color: {ACCENT}; }}
    #files-panel {{ height: 1fr; }}
    #params-panel {{ height: auto; }}
    #preview-panel {{ height: 1fr; }}
    #log-panel {{ height: 10; }}

    #dir-row {{ height: 1; }}
    FileTree {{ height: 1fr; background: transparent; padding: 0; margin-top: 1;
                scrollbar-size-vertical: 1; }}
    FileTree:focus {{ background: transparent; }}
    FileTree > .tree--cursor {{ background: {ACCENT} 30%; }}
    FileTree:focus > .tree--cursor {{ background: {ACCENT} 45%; text-style: bold; }}

    .row {{ height: 1; }}
    .key {{ width: 8; color: {DIM}; }}
    Input {{ border: none; height: 1; padding: 0 1; background: $surface-lighten-1; }}
    Input:focus {{ border: none; background: $surface-lighten-2; }}
    Input > .input--placeholder {{ color: {DIM}; }}
    .row Input {{ width: 1fr; }}
    #prompt Input {{ background: transparent; }}
    #prompt Input:focus {{ background: transparent; }}
    #tz-custom {{ margin-left: 2; }}
    Select {{ width: 18; height: 1; }}
    Select > SelectCurrent {{ border: none; height: 1; padding: 0 1;
                              background: $surface-lighten-1; }}
    Select:focus > SelectCurrent {{ border: none; background: $surface-lighten-2; }}
    Select > SelectOverlay {{ width: 26; }}

    #preview-scroll {{ scrollbar-size-vertical: 1; }}
    #log {{ background: transparent; scrollbar-size-vertical: 1; }}
    #hints {{ height: 1; color: {DIM}; }}
    """

    def __init__(self, start_dir='.'):
        super().__init__()
        self.start_dir = Path(start_dir).expanduser().resolve()
        self._output_touched = False  # the user edited the output path by hand
        self.cfg = None               # report.toml, if found

    # ------------------------------------------------------------ layout ----

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id='header')
        with Horizontal(id='prompt'):
            yield Static('>', id='prompt-mark')
            yield Input(placeholder='путь к jmeter.jtl (или выберите файл в дереве)', id='jtl')
        with Horizontal(id='columns'):
            with Vertical(id='left'):
                with Vertical(id='files-panel', classes='panel'):
                    with Horizontal(id='dir-row'):
                        yield Static('папка', classes='key')
                        yield Input(value=str(self.start_dir), id='dir')
                    yield FileTree(self.start_dir, id='tree')
                with Vertical(id='params-panel', classes='panel'):
                    with Horizontal(classes='row'):
                        yield Static('excel', classes='key')
                        yield Input(placeholder='report.xlsx', id='output')
                    with Horizontal(classes='row'):
                        yield Static('std', id='standard-key', classes='key')
                        yield Input(placeholder='standardResults.xml', id='standard')
                    with Horizontal(classes='row'):
                        yield Static('dash', id='dashboard-key', classes='key')
                        yield Input(placeholder='dashBoard_jmeter.xml', id='dashboard')
                    with Horizontal(classes='row'):
                        yield Static('tz', classes='key')
                        yield Select(TIMEZONES, value='local', allow_blank=False, id='tz')
                        yield Input(placeholder='свой: Europe/Samara, +05:00', id='tz-custom')
                    with Horizontal(classes='row'):
                        yield Static('шаги', classes='key')
                        yield Input(value=DEFAULT_STEP_PATTERN, id='steps')
                    with Horizontal(classes='row'):
                        yield Static('эталон', classes='key')
                        yield Input(placeholder='JTL до изменений для сравнения (Ctrl+E)',
                                    id='baseline')
                    with Horizontal(classes='row'):
                        yield Static('экспорт', classes='key')
                        yield Select(EXPORT_CHOICES, value='config', allow_blank=False,
                                     id='export')
            with Vertical(id='right'):
                with Vertical(id='preview-panel', classes='panel'):
                    with VerticalScroll(id='preview-scroll'):
                        yield Static(Text('Выберите файл, чтобы увидеть предпросмотр.',
                                          style=DIM), id='preview')
                with Vertical(id='log-panel', classes='panel'):
                    yield RichLog(id='log', wrap=True, markup=True, highlight=False)
        yield Static('ctrl+r создать   ctrl+o файлы   ctrl+u/backspace выше   ctrl+b открыть папку   '
                     'ctrl+f тип   ctrl+e эталон   tab дальше   ctrl+q выход', id='hints')

    @staticmethod
    def _header_text():
        text = Text()
        text.append('* ', style=f'bold {ACCENT}')
        text.append('JMeter -> Excel', style='bold')
        text.append('   отчет по результатам JMeter со сверкой с XML из Jenkins', style=DIM)
        return text

    def on_mount(self):
        self.register_theme(THEME)
        self.theme = 'claude-report'
        self.query_one('#files-panel').border_title = self._files_title(FILE_TYPES['jmeter'][0])
        self.query_one('#params-panel').border_title = 'параметры'
        self.query_one('#preview-panel').border_title = 'предпросмотр'
        self.query_one('#log-panel').border_title = 'журнал'
        tree = self.query_one(FileTree)
        tree.root.expand()
        tree.focus()
        self._refresh_notes()
        self._load_config()
        self.say('Выберите .jtl в дереве (Enter) и нажмите Ctrl+R.', DIM)

    def _load_config(self):
        """report.toml from the start folder or the current one: defaults and SLA."""
        try:
            self.cfg = config.load_for(None, self.start_dir, Path.cwd())
        except ReportError as exc:
            self.cfg = None
            self.headline('Ошибка в report.toml', ERR)
            for line in str(exc).splitlines():
                self.say(line, ERR)
            return
        if self.cfg is None:
            return
        if self.cfg.steps:
            self.query_one('#steps', Input).value = self.cfg.steps
        if self.cfg.timezone:
            self.query_one('#tz-custom', Input).value = self.cfg.timezone
        extras = []
        if self.cfg.sla:
            extras.append('SLA')
        if self.cfg.exports:
            extras.append('экспорт: ' + ', '.join(self.cfg.exports))
        self.say(f'конфиг: {short_path(self.cfg.path)}'
                 + (f' ({", ".join(extras)})' if extras else ''), DIM)

    def _default_output(self, jtl_path):
        """default_output_path, but into output_dir from the config when it is set."""
        path = default_output_path(jtl_path)
        if self.cfg and self.cfg.output_dir:
            return Path(self.cfg.output_dir).expanduser() / path.name
        return path

    @staticmethod
    def _files_title(label):
        return f'файлы: {label}'

    # ------------------------------------------------------------ events ----

    @on(DirectoryTree.FileSelected)
    def _file_selected(self, event):
        path = Path(event.path)
        if path.suffix.lower() == '.xml':
            field = '#dashboard' if classify_xml(path) == 'dashboard' else '#standard'
            self.query_one(field, Input).value = str(path)
            self._show_preview(path)
            return
        self.query_one('#jtl', Input).value = str(path)
        if not self._output_touched:
            self.query_one('#output', Input).value = str(self._default_output(path))
        standard, dashboard = find_xml_artifacts(path)
        self.query_one('#standard', Input).value = standard
        self.query_one('#dashboard', Input).value = dashboard
        self._show_preview(path)

    @on(DirectoryTree.NodeHighlighted)
    def _node_highlighted(self, event):
        data = event.node.data
        if data is not None and Path(data.path).is_file():
            self._show_preview(Path(data.path))

    @on(Input.Submitted, '#dir')
    def _dir_submitted(self, event):
        if not event.value.strip():  # an emptied field: put the current folder back
            event.input.value = str(self.start_dir)
            return
        self._set_root(event.value)

    @on(Input.Changed, '#output')
    def _output_changed(self, event):
        # Auto-fill also triggers Changed, so compare with the expected value.
        jtl = self.query_one('#jtl', Input).value.strip()
        expected = str(self._default_output(jtl)) if jtl else ''
        self._output_touched = bool(event.value) and event.value != expected

    @on(Input.Changed, '#standard, #dashboard')
    def _xml_changed(self, event):
        self._refresh_notes()

    @on(Input.Submitted, '#jtl, #output, #standard, #dashboard, #tz-custom, #steps')
    def _submitted(self, event):
        self.action_build()

    # ----------------------------------------------------------- folders ----

    def _set_root(self, raw):
        """Show another directory in the tree (any path on the machine)."""
        raw = (raw or '').strip()
        if not raw:
            return
        path = Path(raw).expanduser()
        if not path.is_dir():
            self.headline(f'Папка не найдена: {raw}', ERR)
            return
        path = path.resolve()
        tree = self.query_one(FileTree)
        tree.path = path
        tree.reload()
        tree.root.expand()
        self.start_dir = path
        self.query_one('#dir', Input).value = str(path)
        tree.focus()

    def action_folder_up(self):
        self._set_root(str(self.start_dir.parent))

    def action_open_folder(self):
        """Make the highlighted folder the root of the tree."""
        node = self.query_one(FileTree).cursor_node
        data = node.data if node is not None else None
        if data is not None and Path(data.path).is_dir():
            self._set_root(str(data.path))

    # ----------------------------------------------------------- preview ----

    def _show_preview(self, path):
        if path.suffix.lower() not in PREVIEWABLE:
            return
        steps = self.query_one('#steps', Input).value.strip() or DEFAULT_STEP_PATTERN
        self._preview_worker(str(path), steps)

    @work(thread=True, exclusive=True, group='preview')
    def _preview_worker(self, path, steps):
        try:
            if path.lower().endswith('.xml'):
                info = preview.summarize_xml(path)
                renderable = preview.render_xml_summary(info, DIM)
            else:
                info = preview.summarize_jtl(path, step_pattern=steps)
                renderable = preview.render_summary(info, ACCENT, DIM, OK, ERR)
        except ReportError as exc:
            renderable = Text(f'Не удается показать файл: {exc}', style=WARN)
        except Exception as exc:  # a broken file must not kill the UI
            renderable = Text(f'Не удается показать файл: {type(exc).__name__}: {exc}',
                              style=WARN)
        self.call_from_thread(self.query_one('#preview', Static).update, renderable)

    # ----------------------------------------------------------- actions ----

    def _refresh_notes(self):
        """Mark the std/dash labels: '+' found (green), '!' not found (red), '-' not used."""
        for name, title in (('standard', 'std'), ('dashboard', 'dash')):
            value = self.query_one(f'#{name}', Input).value.strip()
            key = self.query_one(f'#{name}-key', Static)
            if not value:
                key.update(Text(f'{title} -', style=DIM))
            elif Path(value).expanduser().is_file():
                key.update(Text(f'{title} +', style=OK))
            else:
                key.update(Text(f'{title} !', style=ERR))

    def action_set_baseline(self):
        """Use the highlighted file in the tree as the baseline run for comparison."""
        node = self.query_one(FileTree).cursor_node
        data = node.data if node is not None else None
        if data is not None and Path(data.path).is_file() \
                and Path(data.path).suffix.lower() in ('.jtl', '.csv'):
            self.query_one('#baseline', Input).value = str(data.path)
            self.say(f'эталон: {short_path(data.path)}', DIM)
        else:
            self.headline('Выберите в дереве файл .jtl и нажмите Ctrl+E', ERR)

    def action_focus_files(self):
        self.query_one(FileTree).focus()

    def action_toggle_filter(self):
        tree = self.query_one(FileTree)
        key = 'all' if tree.extensions is not None else 'jmeter'
        tree.extensions = FILE_TYPES[key][1]
        tree.reload()
        self.query_one('#files-panel').border_title = self._files_title(FILE_TYPES[key][0])

    def say(self, text, color=None, bullet='-'):
        line = Text()
        line.append(f'{bullet} ', style=color or '')
        line.append(text, style=color or '')
        self.query_one('#log', RichLog).write(line)

    def headline(self, text, color):
        line = Text()
        line.append('* ', style=f'bold {color}')
        line.append(text, style='bold')
        self.query_one('#log', RichLog).write(line)

    def action_show_history(self):
        output = self.query_one('#output', Input).value.strip()
        jtl = self.query_one('#jtl', Input).value.strip()
        target = output or (str(self._default_output(jtl)) if jtl else str(Path.cwd() / 'x'))
        entries = history.read(Path(target).expanduser())
        if not entries:
            self.headline('История пуста: здесь еще не строили отчеты', DIM)
            return
        self.headline(f'История запусков ({len(entries)})', ACCENT)
        for entry in entries[-10:]:
            self.say(history.format_entry(entry), DIM)

    def action_build(self):
        jtl = self.query_one('#jtl', Input).value.strip()
        output = self.query_one('#output', Input).value.strip()
        standard = self.query_one('#standard', Input).value.strip()
        dashboard = self.query_one('#dashboard', Input).value.strip()
        custom_tz = self.query_one('#tz-custom', Input).value.strip()
        tz_value = custom_tz or self.query_one('#tz', Select).value
        steps = self.query_one('#steps', Input).value.strip() or DEFAULT_STEP_PATTERN
        baseline = self.query_one('#baseline', Input).value.strip()
        export_choice = self.query_one('#export', Select).value

        if not jtl:
            self.headline('Не выбран входной файл', ERR)
            return
        if not Path(jtl).expanduser().is_file():
            self.headline(f'Файл не найден: {jtl}', ERR)
            return
        for label, path in (('standardResults.xml', standard), ('dashBoard_jmeter.xml', dashboard)):
            if path and not Path(path).expanduser().is_file():
                self.headline(f'{label} не найден: {path}', ERR)
                return
        if baseline and not Path(baseline).expanduser().is_file():
            self.headline(f'Эталон не найден: {baseline}', ERR)
            return
        if not output:
            output = str(self._default_output(jtl))
            self.query_one('#output', Input).value = output
        if not output.lower().endswith('.xlsx'):
            self.headline('Выходной файл должен иметь расширение .xlsx', ERR)
            return
        try:
            tz = resolve_timezone(str(tz_value))
        except ReportError as exc:
            self.headline(str(exc).splitlines()[0], ERR)
            return

        try:
            Path(output).expanduser().parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.headline(f'Не удалось создать папку для отчета: {exc}', ERR)
            return

        self.headline('Строю отчет...', ACCENT)
        self._build_worker(
            str(Path(jtl).expanduser()), str(Path(output).expanduser()), tz, steps,
            str(Path(standard).expanduser()) if standard else None,
            str(Path(dashboard).expanduser()) if dashboard else None,
            str(Path(baseline).expanduser()) if baseline else None,
            EXPORT_FORMATS_BY_CHOICE.get(export_choice))

    @work(thread=True, exclusive=True, group='build')
    def _build_worker(self, jtl, output, tz, steps, standard, dashboard, baseline, exports):
        try:
            keep = self.cfg.keep_history if self.cfg else True
            side = list(workflow.extra_paths(output).values())
            info = convert.create_excel_report(
                jtl, output, tz=tz, step_pattern=steps,
                standard_xml=standard, dashboard_xml=dashboard,
                include_raw_data=self.cfg.include_raw_data if self.cfg else True,
                archive=(lambda: history.archive_existing(output, side)) if keep else None)
            # The Excel report is done; extras must not hide that if they fail.
            info['extras'], info['extras_error'] = None, None
            try:
                info['extras'] = workflow.run_extras(
                    jtl, output, self.cfg, tz, steps, baseline=baseline, exports=exports,
                    run=info.get('run'))
            except ReportError as exc:
                info['extras_error'] = str(exc)
            if keep:
                history.record(output, jtl, info, info['extras'], info['archived'])
        except ReportError as exc:
            self.call_from_thread(self._build_failed, str(exc))
        except Exception as exc:  # an unexpected error must not kill the UI
            self.call_from_thread(self._build_failed, f'{type(exc).__name__}: {exc}')
        else:
            self.call_from_thread(self._build_done, info)

    def _build_failed(self, message):
        self.headline('Ошибка', ERR)
        for line in message.splitlines():
            self.say(line, ERR)

    def _build_done(self, info):
        self.say(f'выборок: {info["rows"]}, меток: {info["labels"]}, '
                 f'шагов на графике: {info["steps"]}, ошибок: {info["errors"]}', DIM)
        self.say(f'{info["start"]} -> {info["end"]} ({info["timezone"]}), {info["duration"]}', DIM)
        check = info['verification']
        if check is None:
            self.say('XML не указаны: сверка не выполнялась', DIM)
        elif check['ok']:
            self.say(f'сверка с XML: все {check["checked"]} значений совпали', OK)
        else:
            self.say(f'сверка с XML: расхождений {check["mismatches"]} из {check["checked"]} '
                     f'(в Excel-отчет не попадает)', WARN)
            for row in check['details'][:5]:
                self.say(f'  {row["label"][:30]} / {row["metric"]}: в XML {row["expected"]}, '
                         f'по JTL {row["actual"]}', WARN)
        for warning in info['warnings']:
            if not warning.startswith('сверка'):
                self.say(f'внимание: {warning}', WARN)
        self._show_extras(info)
        for path in info.get('archived') or []:
            self.say(f'прошлая версия сохранена: history/{path.name}', DIM)
        self.headline(f'Готово: {info["output"]}', OK)

    def _show_extras(self, info):
        if info.get('extras_error'):
            self.say(f'доп. результаты не построены: {info["extras_error"]}', ERR)
        extras = info.get('extras')
        if not extras:
            return
        verdict = extras['verdict']
        if verdict is not None:
            if verdict.passed:
                self.say(f'SLA PASS: проверено {verdict.checked}', OK)
            else:
                self.say(f'SLA FAIL: нарушений {len(verdict.failed)} из {verdict.checked}', ERR)
                for row in verdict.failed[:5]:
                    sign = '>' if row['kind'] == 'max' else '<'
                    self.say(f'  {row["label"][:40]}: {row["limit"]} '
                             f'{row["actual"]:g} {sign} {row["bound"]:g}', ERR)
                if len(verdict.failed) > 5:
                    self.say(f'  ... и еще {len(verdict.failed) - 5}', ERR)
        comparison = extras['comparison']
        if comparison is not None:
            color = ERR if comparison.has_regressions else OK
            self.say(f'сравнение (допуск {comparison.tolerance:g}%): хуже '
                     f'{comparison.count("regression")}, лучше {comparison.count("improvement")}, '
                     f'без изменений {comparison.count("same")}', color)
            for row in comparison.regressions[:5]:
                self.say(f'  хуже: {row["label"][:40]}: avg {compare.format_delta(row["avg_delta"])}'
                         f', p90 {compare.format_delta(row["p90_delta"])}', ERR)
        for path in extras['files']:
            self.say(f'файл: {path}', DIM)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    start = argv[0] if argv else '.'
    if not Path(start).expanduser().is_dir():
        sys.exit(f"Каталог не найден: '{start}'")
    ReportApp(start).run()


if __name__ == '__main__':
    main()
