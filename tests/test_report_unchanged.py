"""The Excel report must stay exactly as it was: new features live in separate outputs."""
import hashlib
from pathlib import Path

from openpyxl import load_workbook

from jmeter_reporter import convert
from jmeter_reporter.timeutil import resolve_timezone

SAMPLES = Path(__file__).resolve().parent.parent / 'samples'
# sha256 over sheet names, chart counts, every cell value and number format of the report
# (no 'Сверка' sheet since 1.3: it is not for the customer; the other sheets are byte-for-byte as before)
GOLDEN = 'eb43fa4ffdcd29f8188fb5527df234f7df709937c82406aa83e8166f165aca88'


def fingerprint(path):
    digest = hashlib.sha256()
    for ws in load_workbook(path).worksheets:
        digest.update(ws.title.encode())
        digest.update(str(len(ws._charts)).encode())
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    digest.update(
                        f'{ws.title}!{cell.coordinate}={cell.value!r}|{cell.number_format}'.encode())
    return digest.hexdigest()


def test_excel_report_is_unchanged(tmp_path):
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(
        str(SAMPLES / 'jmeter.jtl'), str(out), tz=resolve_timezone('UTC'),
        standard_xml=str(SAMPLES / 'standardResults.xml'),
        dashboard_xml=str(SAMPLES / 'dashBoard_jmeter.xml'))
    assert fingerprint(out) == GOLDEN


def test_extras_do_not_touch_the_report(tmp_path):
    from jmeter_reporter import workflow
    out = tmp_path / 'r.xlsx'
    convert.create_excel_report(str(SAMPLES / 'jmeter.jtl'), str(out))
    before = out.read_bytes()
    workflow.run_extras(str(SAMPLES / 'jmeter.jtl'), str(out), exports=['html', 'csv'])
    assert out.read_bytes() == before
