"""History: the old report is archived, never silently lost; the journal is readable."""
import os

import config
import convert
import history


def _touch(path, text='x', mtime=1_700_000_000):
    path.write_text(text)
    os.utime(path, (mtime, mtime))


def test_archive_moves_old_report_with_its_own_timestamp(tmp_path):
    out = tmp_path / 'r.xlsx'
    _touch(out)
    moved = history.archive_existing(out)
    assert not out.exists()
    assert len(moved) == 1 and moved[0].parent.name == 'history'
    assert moved[0].name.startswith('r_2023') and moved[0].suffix == '.xlsx'


def test_archive_nothing_to_do(tmp_path):
    assert history.archive_existing(tmp_path / 'none.xlsx') == []
    assert not (tmp_path / 'history').exists()


def test_archive_never_overwrites_an_earlier_archive(tmp_path):
    out = tmp_path / 'r.xlsx'
    for _ in range(3):
        _touch(out)
        history.archive_existing(out)
    assert len(list((tmp_path / 'history').glob('r_*.xlsx'))) == 3


def test_archive_side_files(tmp_path):
    out, side = tmp_path / 'r.xlsx', tmp_path / 'r.html'
    _touch(out)
    _touch(side)
    assert len(history.archive_existing(out, [side, tmp_path / 'r.csv'])) == 2


def test_journal_roundtrip_and_format(tmp_path):
    out = tmp_path / 'r.xlsx'
    info = {'rows': 10, 'errors': 2, 'duration': '1 мин', 'verification': {'ok': False}}
    history.record(out, '/a/run.jtl', info)
    history.record(out, '/a/run2.jtl', dict(info, verification=None))
    entries = history.read(out)
    assert [e['jtl'] for e in entries] == ['run.jtl', 'run2.jtl']
    assert 'XML: расхождения' in history.format_entry(entries[0])
    assert history.read(tmp_path / 'empty' / 'r.xlsx') == []


def test_journal_skips_broken_lines(tmp_path):
    out = tmp_path / 'r.xlsx'
    history.record(out, 'a.jtl', {})
    with open(tmp_path / 'history' / history.JOURNAL_NAME, 'a') as handle:
        handle.write('not json\n')
    assert len(history.read(out)) == 1


def test_cli_second_run_keeps_first_report(tmp_path, sample_jtl):
    out = tmp_path / 'r.xlsx'
    for _ in range(2):
        convert.main([str(sample_jtl), str(out)])
    assert out.exists()
    assert len(list((tmp_path / 'history').glob('r_*.xlsx'))) == 1
    assert len(history.read(out)) == 2


def test_keep_history_can_be_disabled(tmp_path, sample_jtl):
    (tmp_path / 'report.toml').write_text('[report]\nkeep_history = false\n')
    out = tmp_path / 'r.xlsx'
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        for _ in range(2):
            convert.main([str(sample_jtl), str(out)])
    finally:
        os.chdir(cwd)
    assert not (tmp_path / 'history').exists()


def test_keep_history_must_be_bool(tmp_path):
    path = tmp_path / 'report.toml'
    path.write_text('[report]\nkeep_history = "yes"\n')
    try:
        config.load_config(path)
    except convert.ReportError as exc:
        assert 'keep_history' in str(exc)
    else:
        raise AssertionError('no error')
