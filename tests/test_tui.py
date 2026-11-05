import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, RichLog, Select

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
    (tmp_path / '.hidden.jtl').write_text('x')
    (tmp_path / 'sub').mkdir()

    async def scenario():
        app = tui.ReportApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert _tree_names(app) == {'a.jtl', 'b.csv', 'sub'}
            app.query_one('#file-type', Select).value = 'all'
            await pilot.pause()
            await pilot.pause()
            assert _tree_names(app) == {'a.jtl', 'b.csv', 'c.txt', 'sub'}

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
