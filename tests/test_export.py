import csv

import pytest

import convert
import export
import sla
import stats


def test_csv_contents(sample_jtl, tmp_path):
    run = stats.load_run(sample_jtl)
    out = tmp_path / 'r.csv'
    export.write_csv(run, out)
    raw = out.read_bytes()
    assert raw.startswith(b'\xef\xbb\xbf')  # BOM: Excel reads UTF-8 correctly
    rows = list(csv.reader(raw.decode('utf-8-sig').splitlines()))
    assert rows[0] == export.CSV_HEADERS
    assert len(rows) == len(run.labels) + 2 and rows[-1][0] == 'TOTAL'
    assert int(rows[-1][1]) == run.rows


def test_csv_steps_only(sample_jtl, tmp_path):
    run = stats.load_run(sample_jtl)
    out = tmp_path / 'r.csv'
    export.write_csv(run, out, step_pattern=r'^\d{2}\.')
    assert len(out.read_text(encoding='utf-8-sig').splitlines()) == 1 + 10 + 1


def test_html_contains_steps_and_facts(sample_jtl):
    run = stats.load_run(sample_jtl)
    page = export.render_html(run, convert.resolve_timezone('UTC'), r'^\d{2}\.')
    assert page.startswith('<!DOCTYPE html>')
    assert '01. Home page' in page and '10. Logout' in page and 'TOTAL' in page
    assert '15.01.2026 10:00' in page and 'UTC+00:00' in page
    assert 'SLA' not in page
    assert 'sub-request' not in page and 'home page-0' not in page  # steps only


def test_html_escapes_labels(make_run):
    run = make_run([('01. <script>alert(1)</script>', 10, True)])
    page = export.render_html(run)
    assert '<script>alert' not in page and '&lt;script&gt;' in page


def test_html_shows_sla_verdict(make_run):
    run = make_run([('01. A', 500, True)])
    verdict = sla.evaluate(run, sla.normalize({'p90_ms': 100}))
    page = export.render_html(run, verdict=verdict)
    assert 'SLA FAIL' in page and 'Нарушения SLA' in page and '>FAIL<' in page
    ok = sla.evaluate(run, sla.normalize({'p90_ms': 1000}))
    assert 'SLA PASS' in export.render_html(run, verdict=ok)


def test_write_errors(sample_jtl, tmp_path):
    run = stats.load_run(sample_jtl)
    with pytest.raises(convert.ReportError, match='сохранить'):
        export.write_csv(run, tmp_path / 'no' / 'x.csv')
    with pytest.raises(convert.ReportError, match='сохранить'):
        export.write_html(run, tmp_path / 'no' / 'x.html')
