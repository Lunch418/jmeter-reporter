import pytest

import config
import convert
import workflow


def cfg_with(tmp_path, text):
    path = tmp_path / 'report.toml'
    path.write_text(text, encoding='utf-8')
    return config.load_config(str(path))


def test_extra_paths():
    paths = workflow.extra_paths('/x/report.xlsx')
    assert paths == {'compare': '/x/report_compare.xlsx', 'html': '/x/report.html',
                     'csv': '/x/report.csv'}


def test_nothing_requested_does_nothing(sample_jtl, tmp_path):
    out = tmp_path / 'r.xlsx'
    result = workflow.run_extras(str(sample_jtl), str(out))
    assert result == {'verdict': None, 'comparison': None, 'files': []}
    assert list(tmp_path.glob('r*')) == []


def test_exports_and_comparison(sample_jtl, slow_jtl, tmp_path):
    out = tmp_path / 'r.xlsx'
    result = workflow.run_extras(str(sample_jtl), str(out), baseline=str(slow_jtl),
                                 exports=['html', 'csv'])
    assert result['comparison'] is not None and result['verdict'] is None
    assert sorted(p.split('/')[-1] for p in result['files']) == [
        'r.csv', 'r.html', 'r_compare.xlsx']
    assert all((tmp_path / n).exists() for n in ('r.csv', 'r.html', 'r_compare.xlsx'))


def test_config_drives_sla_exports_and_tolerance(sample_jtl, slow_jtl, tmp_path):
    cfg = cfg_with(tmp_path, '[compare]\ntolerance_pct = 1\n[export]\nformats = ["csv"]\n'
                             '[sla]\np90_ms = 100\n')
    out = tmp_path / 'r.xlsx'
    result = workflow.run_extras(str(sample_jtl), str(out), cfg=cfg, baseline=str(slow_jtl))
    assert result['verdict'] is not None and not result['verdict'].passed
    assert result['comparison'].tolerance == 1
    assert (tmp_path / 'r.csv').exists() and not (tmp_path / 'r.html').exists()


def test_explicit_exports_override_config(sample_jtl, tmp_path):
    cfg = cfg_with(tmp_path, '[export]\nformats = ["csv"]\n')
    out = tmp_path / 'r.xlsx'
    result = workflow.run_extras(str(sample_jtl), str(out), cfg=cfg, exports=[])
    assert result['files'] == []


def test_html_includes_verdict_from_config(sample_jtl, tmp_path):
    cfg = cfg_with(tmp_path, '[export]\nformats = ["html"]\n[sla]\np90_ms = 100\n')
    out = tmp_path / 'r.xlsx'
    workflow.run_extras(str(sample_jtl), str(out), cfg=cfg)
    assert 'SLA FAIL' in (tmp_path / 'r.html').read_text(encoding='utf-8')


def test_bad_input_raises(tmp_path):
    bad = tmp_path / 'bad.jtl'
    bad.write_text('a,b\n1,2\n', encoding='utf-8')
    with pytest.raises(convert.ReportError):
        workflow.run_extras(str(bad), str(tmp_path / 'r.xlsx'), exports=['csv'])
