"""CSV and HTML exports of a run (the Excel report is produced by convert.py)."""
import csv
import html
import os

from . import convert

CSV_HEADERS = ['label', 'samples', 'avg', 'median', 'p90', 'p95', 'p99', 'min', 'max',
               'error_pct', 'throughput', 'received_kb_s', 'sent_kb_s']
STAT_KEYS = ['samples', 'avg', 'median', 'p90', 'p95', 'p99', 'min', 'max', 'error_pct',
             'throughput', 'received_kb', 'sent_kb']


def _rows(run, step_pattern=None):
    labels = run.steps(step_pattern) if step_pattern else list(run.labels)
    return [run.labels[label] for label in labels] + [run.total]


def write_csv(run, path, step_pattern=None):
    """Summary table, one row per label plus TOTAL. UTF-8 with BOM so Excel opens it right."""
    try:
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
            for stats in _rows(run, step_pattern):
                writer.writerow([convert.csv_safe(stats['label'])] + [
                    round(stats[k], 3) if isinstance(stats[k], float) else stats[k]
                    for k in STAT_KEYS])
    except OSError as exc:
        raise convert.ReportError(f"Не удалось сохранить '{path}': {exc}")


CSS = """
:root { color-scheme: light dark; --accent: #d97757; --line: #8884; --dim: #888; }
body { font: 14px/1.5 system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; }
h1 { font-size: 1.4rem; margin-bottom: .2rem; } .dim { color: var(--dim); }
.facts { display: flex; gap: 2rem; flex-wrap: wrap; margin: 1rem 0; }
.facts b { display: block; font-size: 1.2rem; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { padding: .3rem .6rem; border-bottom: 1px solid var(--line); text-align: right; }
th:first-child, td:first-child { text-align: left; } th { color: var(--dim); font-weight: 500; }
tr.total td { font-weight: 600; border-top: 2px solid var(--line); }
.bar { display: inline-block; height: .7rem; background: var(--accent); border-radius: 2px; }
.bad { color: #d33; } .ok { color: #2a8a3e; }
.badge { padding: .1rem .5rem; border-radius: 3px; font-weight: 600; font-size: .85rem; }
.badge.pass { background: #2a8a3e22; color: #2a8a3e; } .badge.fail { background: #d3333322; color: #d33; }
"""


def _fmt(value):
    return f'{value:.1f}' if isinstance(value, float) else str(value)


def render_html(run, tz=None, step_pattern=None, verdict=None, title='Отчет по нагрузочному тестированию'):
    """Self-contained HTML page (open in a browser, print to PDF if you need one)."""
    e = html.escape
    start = convert.format_timestamp(run.first_ts, tz)
    end = convert.format_timestamp(run.last_ts, tz)
    tz_label = convert.timezone_label(run.first_ts, tz)
    errors = run.errors

    rows = _rows(run, step_pattern)
    peak = max((s['avg'] for s in rows[:-1]), default=0) or 1
    failed = set(verdict.failed_labels) if verdict else set()

    body = [f'<h1>{e(title)}</h1>',
            f'<div class="dim">{e(os.path.basename(run.path))} &middot; {e(start)} - '
            f'{e(end)} ({e(tz_label)})</div>']
    if verdict:
        cls, text = ('pass', 'PASS') if verdict.passed else ('fail', 'FAIL')
        body.append(f'<p><span class="badge {cls}">SLA {text}</span> '
                    f'<span class="dim">проверено {verdict.checked}, '
                    f'нарушений {len(verdict.failed)}</span></p>')
    body.append('<div class="facts">'
                f'<div><span class="dim">выборок</span><b>{run.rows}</b></div>'
                f'<div><span class="dim">меток</span><b>{len(run.labels)}</b></div>'
                f'<div><span class="dim">ошибок</span><b class="{"bad" if errors else "ok"}">'
                f'{errors}</b></div>'
                f'<div><span class="dim">длительность</span>'
                f'<b>{e(convert.format_duration(run.duration_ms))}</b></div></div>')

    body.append('<table><thead><tr><th>Label</th><th>n</th><th>avg</th><th>median</th>'
                '<th>p90</th><th>p95</th><th>max</th><th>err %</th><th></th>'
                + ('<th>SLA</th>' if verdict else '') + '</tr></thead><tbody>')
    for stats in rows:
        total = stats['label'] == 'TOTAL'
        width = 0 if total else round(stats['avg'] / peak * 100)
        err_cls = ' class="bad"' if stats['error_pct'] else ''
        cells = (f'<td>{e(stats["label"])}</td><td>{stats["samples"]}</td>'
                 f'<td>{stats["avg"]}</td><td>{stats["median"]}</td><td>{stats["p90"]}</td>'
                 f'<td>{stats["p95"]}</td><td>{stats["max"]}</td>'
                 f'<td{err_cls}>{_fmt(stats["error_pct"])}</td>'
                 f'<td style="width:140px"><span class="bar" style="width:{width}%"></span></td>')
        if verdict:
            if stats['label'] in failed:
                cells += '<td class="bad">FAIL</td>'
            elif any(r['label'] == stats['label'] for r in verdict.rows):
                cells += '<td class="ok">PASS</td>'
            else:
                cells += '<td></td>'
        body.append(f'<tr class="{"total" if total else ""}">{cells}</tr>')
    body.append('</tbody></table>')

    if verdict and verdict.failed:
        body.append('<h2>Нарушения SLA</h2><table><thead><tr><th>Label</th><th>Метрика</th>'
                    '<th>Факт</th><th>Предел</th></tr></thead><tbody>')
        for r in verdict.failed:
            sign = '&le;' if r['kind'] == 'max' else '&ge;'
            body.append(f'<tr><td>{e(r["label"])}</td><td>{e(r["limit"])}</td>'
                        f'<td class="bad">{_fmt(r["actual"])}</td><td>{sign} {r["bound"]:g}</td></tr>')
        body.append('</tbody></table>')
    return ('<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body>'
            + ''.join(body) + '</body></html>')


def write_html(run, path, tz=None, step_pattern=None, verdict=None):
    page = render_html(run, tz, step_pattern, verdict)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(page)
    except OSError as exc:
        raise convert.ReportError(f"Не удалось сохранить '{path}': {exc}")

