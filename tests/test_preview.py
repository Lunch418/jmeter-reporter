import pytest

pytest.importorskip("rich")  # comes with textual; the interface is optional

from rich.console import Console

import convert
import preview


def _text(renderable, width=100):
    console = Console(width=width, record=True, file=open('/dev/null', 'w'))
    console.print(renderable)
    return console.export_text()


def test_summarize_jtl(sample_jtl):
    info = preview.summarize_jtl(sample_jtl)
    assert info['rows'] > 0 and info['labels'] > 10
    assert info['is_steps'] and len(info['rows_table']) == 10
    assert info['truncated'] is False


def test_summary_is_cut_by_limit(sample_jtl):
    info = preview.summarize_jtl(sample_jtl, limit=20)
    assert info['rows'] == 20 and info['truncated'] is True


def test_render_summary_contains_steps_and_bars(sample_jtl):
    text = _text(preview.render_summary(preview.summarize_jtl(sample_jtl)))
    assert '01. Home page' in text and '10. Logout' in text
    assert '#' in text and 'выборок' in text


def test_labels_shown_when_no_numbered_steps(tmp_path):
    f = tmp_path / 'plain.jtl'
    f.write_text('timeStamp,elapsed,label,success\n1,10,login,true\n2,20,home,false\n',
                 encoding='utf-8')
    info = preview.summarize_jtl(f)
    assert not info['is_steps'] and len(info['rows_table']) == 2
    assert info['errors'] == 1


def test_many_labels_are_collapsed(tmp_path):
    f = tmp_path / 'many.jtl'
    rows = ''.join(f'{i},10,label{i},true\n' for i in range(30))
    f.write_text('timeStamp,elapsed,label,success\n' + rows, encoding='utf-8')
    info = preview.summarize_jtl(f)
    assert len(info['rows_table']) == preview.MAX_TABLE_ROWS
    assert info['hidden_labels'] == 30 - preview.MAX_TABLE_ROWS
    assert 'еще 16 меток' in _text(preview.render_summary(info))


def test_bad_files_raise_report_error(tmp_path):
    empty = tmp_path / 'e.jtl'
    empty.write_text('timeStamp,elapsed,label\n', encoding='utf-8')
    with pytest.raises(convert.ReportError):
        preview.summarize_jtl(empty)
    wrong = tmp_path / 'w.jtl'
    wrong.write_text('a,b\n1,2\n', encoding='utf-8')
    with pytest.raises(convert.ReportError, match='колонок'):
        preview.summarize_jtl(wrong)
    xml = tmp_path / 'x.jtl'
    xml.write_text('<testResults/>', encoding='utf-8')
    with pytest.raises(convert.ReportError, match='XML'):
        preview.summarize_jtl(xml)


def test_xml_summary(sample_xml):
    std, dash = sample_xml
    for path in (std, dash):
        info = preview.summarize_xml(path)
        assert info['labels'] == 27 and info['values'] > 27
        assert path.name in _text(preview.render_xml_summary(info))


def test_human_size():
    assert preview.human_size(512) == '512 B'
    assert preview.human_size(2048) == '2.0 KB'
    assert preview.human_size(5 * 1024 ** 2) == '5.0 MB'
