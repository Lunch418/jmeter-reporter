import cli


def write_cfg(tmp_path, text):
    path = tmp_path / 'report.toml'
    path.write_text(text, encoding='utf-8')
    return str(path)


def test_check_passes_with_exit_0(sample_jtl, tmp_path, capsys):
    cfg = write_cfg(tmp_path, '[sla]\np90_ms = 100000\n')
    assert cli.main(['check', str(sample_jtl), '--config', cfg]) == 0
    assert 'PASS: проверено' in capsys.readouterr().out


def test_check_fails_with_exit_1(sample_jtl, tmp_path, capsys):
    cfg = write_cfg(tmp_path, '[sla]\np90_ms = 1\n')
    assert cli.main(['check', str(sample_jtl), '--config', cfg]) == 1
    assert 'FAIL: проверено' in capsys.readouterr().out


def test_check_without_sla_is_an_error(sample_jtl, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(['check', str(sample_jtl)]) == 2
    assert 'Нет раздела [sla]' in capsys.readouterr().err


def test_check_with_broken_config_is_an_error(sample_jtl, tmp_path, capsys):
    cfg = write_cfg(tmp_path, '[sla]\nbogus = 1\n')
    assert cli.main(['check', str(sample_jtl), '--config', cfg]) == 2
    assert 'неизвестное ограничение' in capsys.readouterr().err


def test_check_picks_report_toml_from_cwd(sample_jtl, tmp_path, monkeypatch, capsys):
    write_cfg(tmp_path, '[sla]\np90_ms = 1\n')
    monkeypatch.chdir(tmp_path)
    assert cli.main(['check', str(sample_jtl)]) == 1


def test_check_steps_option(sample_jtl, tmp_path, capsys):
    cfg = write_cfg(tmp_path, '[sla]\np90_ms = 1\n')
    # no label matches -> nothing was checked -> input/config error, not a silent pass
    assert cli.main(['check', str(sample_jtl), '--config', cfg, '--steps', '^ZZZ']) == 2


def test_compare_writes_file(sample_jtl, slow_jtl, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'cmp.xlsx'
    assert cli.main(['compare', str(sample_jtl), str(slow_jtl), '-o', str(out)]) == 0
    assert out.exists() and 'допуск 10%' in capsys.readouterr().out


def test_compare_default_output_next_to_new(sample_jtl, slow_jtl, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(['compare', str(sample_jtl), str(slow_jtl)])
    assert (tmp_path / 'slow_compare.xlsx').exists()


def test_compare_fail_on_regression(sample_jtl, slow_jtl, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = ['compare', str(sample_jtl), str(slow_jtl), '--tolerance', '0']
    assert cli.main(args) == 0
    assert cli.main(args + ['--fail-on-regression']) == 1


def test_compare_same_run_has_no_regressions(sample_jtl, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(['compare', str(sample_jtl), str(sample_jtl),
                     '--fail-on-regression']) == 0


def test_compare_uses_config_tolerance(sample_jtl, slow_jtl, tmp_path, capsys):
    cfg = write_cfg(tmp_path, '[compare]\ntolerance_pct = 77\n')
    cli.main(['compare', str(sample_jtl), str(slow_jtl), '-o', str(tmp_path / 'c.xlsx'),
              '--config', cfg])
    assert 'допуск 77%' in capsys.readouterr().out


def test_compare_bad_file_is_exit_2(sample_jtl, tmp_path, capsys):
    bad = tmp_path / 'bad.jtl'
    bad.write_text('x,y\n', encoding='utf-8')
    assert cli.main(['compare', str(sample_jtl), str(bad), '-o', str(tmp_path / 'c.xlsx')]) == 2


def test_export_html_and_csv(sample_jtl, tmp_path, capsys):
    out = tmp_path / 'rep.xlsx'
    assert cli.main(['export', str(sample_jtl), '--format', 'html', 'csv',
                     '-o', str(out), '--tz', 'UTC']) == 0
    assert (tmp_path / 'rep.html').exists() and (tmp_path / 'rep.csv').exists()


def test_export_single_format_uses_exact_name(sample_jtl, tmp_path):
    target = tmp_path / 'my.html'
    assert cli.main(['export', str(sample_jtl), '-o', str(target)]) == 0
    assert target.exists()


def test_export_default_name_next_to_input(sample_jtl, tmp_path):
    assert cli.main(['export', str(sample_jtl), '--format', 'csv']) == 0
    assert (tmp_path / 'sample_report.csv').exists()


def test_export_includes_sla_from_config(sample_jtl, tmp_path):
    cfg = write_cfg(tmp_path, '[sla]\np90_ms = 1\n')
    target = tmp_path / 'v.html'
    cli.main(['export', str(sample_jtl), '-o', str(target), '--config', cfg])
    assert 'SLA FAIL' in target.read_text(encoding='utf-8')


def test_export_single_format_with_foreign_extension_uses_base_name(sample_jtl, tmp_path):
    out = tmp_path / 'rep.xlsx'
    assert cli.main(['export', str(sample_jtl), '--format', 'html', '-o', str(out)]) == 0
    assert (tmp_path / 'rep.html').exists() and not out.exists()
