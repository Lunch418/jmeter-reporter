import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, RichLog, Static

import tui


def run(coro):
    return asyncio.run(coro)


def log_text(app):
    return '\n'.join(str(line.text) for line in app.query_one('#log', RichLog).lines)


def test_default_output_path():
    assert tui.default_output_path('/a/b/run.jtl') == Path('/a/b/run_report.xlsx')


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
            assert 'найден' in str(app.query_one('#standard-note', Static).render())
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
