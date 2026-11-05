#!/usr/bin/env python3
"""Render the terminal UI to an SVG for the README (uses the synthetic samples).

    # data folder: jmeter.jtl, the two XML, report.toml (copy of report.example.toml)
    # and baseline.jtl (an older run); everything synthetic
    docker run --rm -v "$PWD/samples-copy:/data" --entrypoint python \
        -v "$PWD/docs:/out" jmeter-report /app/tools/make_screenshot.py /out/screenshot.svg
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tui  # noqa: E402
from textual.widgets import Input  # noqa: E402


async def main(data_dir, out_svg):
    app = tui.ReportApp(data_dir)
    async with app.run_test(size=(150, 42)) as pilot:
        await pilot.pause()
        tree = app.query_one(tui.FileTree)
        jtl = Path(data_dir) / 'jmeter.jtl'
        tree.post_message(tui.DirectoryTree.FileSelected(tree.root, jtl))
        await pilot.pause(0.8)
        baseline = Path(data_dir) / 'baseline.jtl'
        if baseline.exists():
            app.query_one('#baseline', Input).value = str(baseline)
        app.action_build()
        await pilot.pause(2.5)
        Path(out_svg).write_text(app.export_screenshot(title='JMeter -> Excel'),
                                 encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[2] if len(sys.argv) > 2 else '/data', sys.argv[1]))
