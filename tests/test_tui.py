import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")  # the interface is optional: skip these tests without it

from textual.widgets import Input, RichLog, Select, Static

import tui


def run(coro):
    return asyncio.run(coro)


def log_text(app):
    return '\n'.join(str(line.text) for line in app.query_one('#log', RichLog).lines)


def test_default_output_path_for_missing_folder_falls_back(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert tui.default_output_path('/no/such/dir/run.jtl') == \
        tmp_path / 'reports' / 'run_report.xlsx'


def _tree_names(app):
    tree = app.query_one(tui.FileTree)
    return {Path(str(n.data.path)).name for n in tree.root.children if n.data}


def test_tree_filters_by_type(tmp_path):
    (tmp_path / 'a.jtl').write_text('x')
    (tmp_path / 'b.csv').write_text('x')
    (tmp_path / 'c.txt').write_text('x')
    (tmp_path / 'd.xml').write_text('x')
    (tmp_path / '.hidden.jtl').write_text('x')
    (tmp_path / 'sub').mkdir()

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert _tree_names(app) == {'a.jtl', 'b.csv', 'd.xml', 'sub'}
            app.action_toggle_filter()
            await pilot.pause()
            await pilot.pause()
            assert _tree_names(app) == {'a.jtl', 'b.csv', 'c.txt', 'd.xml', 'sub'}
            app.action_toggle_filter()
            await pilot.pause()
            await pilot.pause()
            assert _tree_names(app) == {'a.jtl', 'b.csv', 'd.xml', 'sub'}

    run(scenario())


def test_build_without_file_shows_error(tmp_path):
    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            app.action_build()
            await pilot.pause()
            assert 'Не выбран входной файл' in log_text(app)

    run(scenario())


def test_build_rejects_non_xlsx_output(tmp_path, sample_jtl):
    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#output', Input).value = str(tmp_path / 'x.txt')
            app.action_build()
            await pilot.pause()
            assert '.xlsx' in log_text(app)

    run(scenario())


def test_build_with_bad_timezone(tmp_path, sample_jtl):
    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#tz-custom', Input).value = 'Mars/Olympus'
            app.action_build()
            await pilot.pause()
            assert 'Неизвестный часовой пояс' in log_text(app)

    run(scenario())


def test_build_report_end_to_end(tmp_path, sample_jtl):
    out = tmp_path / 'ui.xlsx'

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#output', Input).value = str(out)
            app.query_one('#tz-custom', Input).value = 'UTC'
            app.action_build()
            for _ in range(100):
                await pilot.pause(0.05)
                if out.exists() and 'Готово' in log_text(app):
                    break
            assert 'Готово' in log_text(app)
            assert 'UTC+00:00' in log_text(app)

    run(scenario())
    assert out.exists()


def test_selecting_file_fills_fields(tmp_path, sample_jtl):
    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            tree = app.query_one(tui.FileTree)
            tree.post_message(tui.DirectoryTree.FileSelected(tree.root, sample_jtl))
            await pilot.pause()
            assert app.query_one('#jtl', Input).value == str(sample_jtl)
            assert app.query_one('#output', Input).value.endswith('sample_report.xlsx')

    run(scenario())


def test_main_rejects_missing_dir(tmp_path):
    with pytest.raises(SystemExit):
        tui.main([str(tmp_path / 'nope')])


def test_classify_xml():
    assert tui.classify_xml('/x/dashBoard_jmeter.xml') == 'dashboard'
    assert tui.classify_xml('/x/standardResults.xml') == 'standard'


def test_find_xml_artifacts(tmp_path):
    (tmp_path / 'standardResults.xml').write_text('x')
    (tmp_path / 'DashBoard_jmeter.xml').write_text('x')
    (tmp_path / 'other.xml').write_text('x')
    std, dash = tui.find_xml_artifacts(tmp_path / 'run.jtl')
    assert Path(std).name == 'standardResults.xml'
    assert Path(dash).name == 'DashBoard_jmeter.xml'
    assert tui.find_xml_artifacts(tmp_path / 'nope' / 'run.jtl') == ('', '')


def test_selecting_jtl_autodetects_xml_and_builds_with_check(tmp_path, sample_jtl, sample_xml):
    sample_jtl_in_tmp = sample_jtl  # fixtures share tmp_path, so the XML sit next to it
    out = tmp_path / 'checked.xlsx'

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            tree = app.query_one(tui.FileTree)
            tree.post_message(tui.DirectoryTree.FileSelected(tree.root, sample_jtl_in_tmp))
            await pilot.pause()
            assert app.query_one('#standard', Input).value.endswith('standardResults.xml')
            assert app.query_one('#dashboard', Input).value.endswith('dashBoard_jmeter.xml')
            assert 'std +' in str(app.query_one('#standard-key', Static).render())
            app.query_one('#output', Input).value = str(out)
            app.action_build()
            for _ in range(100):
                await pilot.pause(0.05)
                if 'Готово' in log_text(app):
                    break
            assert 'совпали' in log_text(app)

    run(scenario())


def test_clicking_xml_fills_matching_field(tmp_path):
    xml = tmp_path / 'dashBoard_jmeter.xml'
    xml.write_text('x')

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            tree = app.query_one(tui.FileTree)
            tree.post_message(tui.DirectoryTree.FileSelected(tree.root, xml))
            await pilot.pause()
            assert app.query_one('#dashboard', Input).value == str(xml)
            assert app.query_one('#standard', Input).value == ''
            assert app.query_one('#jtl', Input).value == ''

    run(scenario())


def test_build_with_missing_xml_shows_error(tmp_path, sample_jtl):
    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#standard', Input).value = str(tmp_path / 'missing.xml')
            app.action_build()
            await pilot.pause()
            assert 'не найден' in log_text(app)

    run(scenario())


# --------------------------------------------------- folders and preview ----

def _preview_text(app):
    from rich.console import Console
    console = Console(width=140, record=True, file=open('/dev/null', 'w'))
    console.print(app.query_one('#preview', Static).content)
    return console.export_text()


async def _wait_preview(pilot, app, needle):
    for _ in range(100):
        await pilot.pause(0.05)
        if needle in _preview_text(app):
            return
    raise AssertionError(f'{needle!r} not in preview: {_preview_text(app)!r}')


def test_tree_uses_ascii_icons_not_emoji():
    assert tui.FileTree.ICON_NODE.isascii()
    assert tui.FileTree.ICON_NODE_EXPANDED.isascii()
    assert tui.FileTree.ICON_FILE.isascii()


def test_preview_shows_stats_on_select(tmp_path, sample_jtl):
    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            tree = app.query_one(tui.FileTree)
            tree.post_message(tui.DirectoryTree.FileSelected(tree.root, sample_jtl))
            await _wait_preview(pilot, app, '01. Home page')
            assert 'выборок' in _preview_text(app)

    run(scenario())


def test_preview_of_xml_and_broken_file(tmp_path, sample_xml):
    std, _ = sample_xml
    broken = tmp_path / 'broken.jtl'
    broken.write_text('a,b\n1,2\n', encoding='utf-8')

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            tree = app.query_one(tui.FileTree)
            tree.post_message(tui.DirectoryTree.FileSelected(tree.root, std))
            await _wait_preview(pilot, app, 'значений для сверки')
            tree.post_message(tui.DirectoryTree.FileSelected(tree.root, broken))
            await _wait_preview(pilot, app, 'Не удается показать файл')

    run(scenario())


def test_open_any_directory_via_input(tmp_path):
    other = tmp_path / 'elsewhere'
    other.mkdir()
    (other / 'x.jtl').write_text('x')

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_root(str(other))
            await pilot.pause()
            await pilot.pause()
            assert app.start_dir == other.resolve()
            assert app.query_one('#dir', Input).value == str(other.resolve())
            assert _tree_names(app) == {'x.jtl'}

    run(scenario())


def test_open_missing_directory_shows_error(tmp_path):
    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            app._set_root(str(tmp_path / 'nope'))
            await pilot.pause()
            assert 'Папка не найдена' in log_text(app)
            assert app.start_dir == tmp_path.resolve()

    run(scenario())


def test_folder_up(tmp_path):
    child = tmp_path / 'child'
    child.mkdir()

    async def scenario():
        app = tui.ReportApp(child)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_folder_up()
            await pilot.pause()
            assert app.start_dir == tmp_path.resolve()

    run(scenario())


def test_open_highlighted_folder(tmp_path):
    child = tmp_path / 'child'
    child.mkdir()

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            tree = app.query_one(tui.FileTree)
            tree.select_node(tree.root.children[0])
            tree.move_cursor(tree.root.children[0])
            await pilot.pause()
            app.action_open_folder()
            await pilot.pause()
            assert app.start_dir == child.resolve()

    run(scenario())


# ------------------------------------------------ small UX fixes (v3) ----

def test_default_output_is_next_to_input(tmp_path):
    assert tui.default_output_path(tmp_path / 'run.jtl') == tmp_path / 'run_report.xlsx'


def test_default_output_for_demo_samples_goes_to_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tui.default_output_path(tui.SAMPLES_DIR / 'jmeter.jtl')
    assert out == tmp_path / 'reports' / 'jmeter_report.xlsx'


def test_default_output_for_readonly_folder_goes_to_reports(tmp_path, monkeypatch):
    ro = tmp_path / 'ro'
    ro.mkdir()
    work = tmp_path / 'work'
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setattr(tui.os, 'access', lambda path, mode: False)
    assert tui.default_output_path(ro / 'x.jtl') == work / 'reports' / 'x_report.xlsx'


def test_clutter_folders_are_hidden_in_both_modes(tmp_path):
    for name in ('__pycache__', 'node_modules', 'venv', 'pkg.egg-info', 'real'):
        (tmp_path / name).mkdir()

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert _tree_names(app) == {'real'}
            app.action_toggle_filter()
            await pilot.pause()
            await pilot.pause()
            assert _tree_names(app) == {'real'}

    run(scenario())


def test_xml_status_marks(tmp_path, sample_xml):
    std, _ = sample_xml

    def key(app, name):
        return str(app.query_one(f'#{name}-key', Static).render())

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert key(app, 'standard') == 'std -'
            app.query_one('#standard', Input).value = str(std)
            await pilot.pause()
            assert key(app, 'standard') == 'std +'
            app.query_one('#standard', Input).value = str(tmp_path / 'missing.xml')
            await pilot.pause()
            assert key(app, 'standard') == 'std !'

    run(scenario())


def test_build_creates_missing_reports_folder(tmp_path, sample_jtl):
    out = tmp_path / 'new' / 'deep' / 'r.xlsx'

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#output', Input).value = str(out)
            app.action_build()
            for _ in range(100):
                await pilot.pause(0.05)
                if 'Готово' in log_text(app):
                    break
            assert 'Готово' in log_text(app)

    run(scenario())
    assert out.exists()


# ------------------------------------- config, baseline, export, SLA (v4) ----

def _build_and_wait(app, pilot):
    async def go():
        app.action_build()
        for _ in range(200):
            await pilot.pause(0.05)
            if 'Готово' in log_text(app) or 'Ошибка' in log_text(app):
                break
        await pilot.pause()
    return go()


def test_config_is_loaded_and_applied(tmp_path, monkeypatch):
    (tmp_path / 'report.toml').write_text(
        '[report]\ntimezone = "UTC"\nsteps = "^0[1-2]"\n[sla]\np90_ms = 5\n'
        '[export]\nformats = ["csv"]\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.cfg is not None
            assert app.query_one('#steps', Input).value == '^0[1-2]'
            assert app.query_one('#tz-custom', Input).value == 'UTC'
            assert 'SLA' in log_text(app) and 'экспорт: csv' in log_text(app)

    run(scenario())


def test_broken_config_is_reported_not_fatal(tmp_path, monkeypatch):
    (tmp_path / 'report.toml').write_text('[sla]\nbogus = 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.cfg is None
            assert 'Ошибка в report.toml' in log_text(app)
            assert 'bogus' in log_text(app)

    run(scenario())


def test_set_baseline_from_tree(tmp_path, sample_jtl, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'aaa').mkdir()  # folders are listed first: the cursor starts on a folder

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_set_baseline()  # cursor is on the folder, not a file
            await pilot.pause()
            assert 'Выберите в дереве файл' in log_text(app)
            tree = app.query_one(tui.FileTree)
            node = next(n for n in tree.root.children if n.data.path == sample_jtl)
            tree.move_cursor(node)
            await pilot.pause()
            app.action_set_baseline()
            assert app.query_one('#baseline', Input).value == str(sample_jtl)

    run(scenario())


def test_build_with_baseline_and_exports(tmp_path, sample_jtl, slow_jtl, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'r.xlsx'

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            app.query_one('#jtl', Input).value = str(slow_jtl)
            app.query_one('#output', Input).value = str(out)
            app.query_one('#baseline', Input).value = str(sample_jtl)
            app.query_one('#export', Select).value = 'both'
            await _build_and_wait(app, pilot)
            text = log_text(app)
            assert 'сравнение (допуск 10%)' in text
            assert 'Готово' in text

    run(scenario())
    for name in ('r.xlsx', 'r_compare.xlsx', 'r.html', 'r.csv'):
        assert (tmp_path / name).exists(), name


def test_export_choice_none_overrides_config(tmp_path, sample_jtl, monkeypatch):
    (tmp_path / 'report.toml').write_text('[export]\nformats = ["csv"]\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'r.xlsx'

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#output', Input).value = str(out)
            app.query_one('#export', Select).value = 'none'
            await _build_and_wait(app, pilot)

    run(scenario())
    assert out.exists() and not (tmp_path / 'r.csv').exists()


def test_config_export_used_by_default(tmp_path, sample_jtl, monkeypatch):
    (tmp_path / 'report.toml').write_text('[export]\nformats = ["csv"]\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'r.xlsx'

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#output', Input).value = str(out)
            await _build_and_wait(app, pilot)

    run(scenario())
    assert (tmp_path / 'r.csv').exists()


def test_sla_verdict_is_shown(tmp_path, sample_jtl, monkeypatch):
    (tmp_path / 'report.toml').write_text('[sla]\np90_ms = 5\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#output', Input).value = str(tmp_path / 'r.xlsx')
            await _build_and_wait(app, pilot)
            text = log_text(app)
            assert 'SLA FAIL' in text and 'p90_ms' in text and 'Готово' in text

    run(scenario())


def test_sla_pass_is_shown(tmp_path, sample_jtl, monkeypatch):
    (tmp_path / 'report.toml').write_text('[sla]\np90_ms = 999999\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#output', Input).value = str(tmp_path / 'r.xlsx')
            await _build_and_wait(app, pilot)
            assert 'SLA PASS' in log_text(app)

    run(scenario())


def test_extras_failure_does_not_hide_the_report(tmp_path, sample_jtl, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / 'bad.jtl'
    bad.write_text('a,b\n1,2\n', encoding='utf-8')
    out = tmp_path / 'r.xlsx'

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#output', Input).value = str(out)
            app.query_one('#baseline', Input).value = str(bad)
            await _build_and_wait(app, pilot)
            text = log_text(app)
            assert 'доп. результаты не построены' in text and 'Готово' in text

    run(scenario())
    assert out.exists()


def test_missing_baseline_is_rejected(tmp_path, sample_jtl, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            app.query_one('#jtl', Input).value = str(sample_jtl)
            app.query_one('#baseline', Input).value = str(tmp_path / 'nope.jtl')
            app.action_build()
            await pilot.pause()
            assert 'Эталон не найден' in log_text(app)

    run(scenario())


def test_output_dir_from_config(tmp_path, sample_jtl, monkeypatch):
    (tmp_path / 'report.toml').write_text('[report]\noutput_dir = "out"\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            tree = app.query_one(tui.FileTree)
            tree.post_message(tui.DirectoryTree.FileSelected(tree.root, sample_jtl))
            await pilot.pause()
            assert app.query_one('#output', Input).value == str(Path('out') / 'sample_report.xlsx')

    run(scenario())


# ---------------------------------------------- navigation keys (v5) ----

def test_root_is_not_shown_so_it_cannot_be_collapsed(tmp_path):
    (tmp_path / 'a.jtl').write_text('x')

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            tree = app.query_one(tui.FileTree)
            assert tree.show_root is False and tree.root.is_expanded
            assert _tree_names(app) == {'a.jtl'}

    run(scenario())


def test_ctrl_u_goes_up_from_an_input_and_does_not_clear_it(tmp_path):
    child = tmp_path / 'child'
    child.mkdir()

    async def scenario():
        app = tui.ReportApp(child)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one('#dir', Input).focus()
            await pilot.pause()
            await pilot.press('ctrl+u')
            await pilot.pause()
            assert app.start_dir == tmp_path.resolve()
            assert app.query_one('#dir', Input).value == str(tmp_path.resolve())

    run(scenario())


def test_ctrl_u_from_the_jtl_prompt_keeps_the_prompt_text(tmp_path):
    child = tmp_path / 'child'
    child.mkdir()

    async def scenario():
        app = tui.ReportApp(child)
        async with app.run_test() as pilot:
            await pilot.pause()
            prompt = app.query_one('#jtl', Input)
            prompt.value = '/some/file.jtl'
            prompt.focus()
            await pilot.pause()
            await pilot.press('ctrl+u')
            await pilot.pause()
            assert prompt.value == '/some/file.jtl'  # not wiped by the Input's own binding

    run(scenario())


def test_ctrl_f_toggles_filter_from_an_input(tmp_path):
    (tmp_path / 'c.txt').write_text('x')

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one('#steps', Input).focus()
            await pilot.pause()
            await pilot.press('ctrl+f')
            await pilot.pause()
            await pilot.pause()
            assert 'c.txt' in _tree_names(app)

    run(scenario())


def test_backspace_in_tree_goes_up(tmp_path):
    child = tmp_path / 'child'
    child.mkdir()

    async def scenario():
        app = tui.ReportApp(child)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(tui.FileTree).focus()
            await pilot.pause()
            await pilot.press('backspace')
            await pilot.pause()
            assert app.start_dir == tmp_path.resolve()

    run(scenario())


def test_up_at_filesystem_root_is_harmless():
    async def scenario():
        app = tui.ReportApp('/')
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_folder_up()
            await pilot.pause()
            assert str(app.start_dir) == '/'

    run(scenario())


def test_emptied_folder_field_is_restored_on_enter(tmp_path):
    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            field = app.query_one('#dir', Input)
            field.value = ''
            field.focus()
            await pilot.pause()
            await pilot.press('enter')
            await pilot.pause()
            assert field.value == str(tmp_path.resolve())

    run(scenario())
