from pathlib import Path

import pytest

import config
import convert

ROOT = Path(__file__).resolve().parent.parent


def write(tmp_path, text, name='report.toml'):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return str(path)


def test_example_config_is_valid():
    cfg = config.load_config(str(ROOT / 'report.example.toml'))
    assert cfg.timezone == 'Europe/Moscow'
    assert cfg.steps == r'^\d{2}\.'
    assert cfg.exports == ['html']
    assert cfg.tolerance_pct == 10
    assert cfg.sla['defaults'] == {'p90_ms': 2000.0, 'error_pct': 1.0}
    assert cfg.sla['overrides'][0]['limits'] == {'p90_ms': 5000.0}


def test_defaults_when_sections_missing(tmp_path):
    cfg = config.load_config(write(tmp_path, '[report]\ntimezone = "UTC"\n'))
    assert cfg.sla is None and cfg.exports == [] and cfg.tolerance_pct == 10


@pytest.mark.parametrize('text,match', [
    ('[nope]\nx = 1\n', 'неизвестные разделы'),
    ('[report]\ntimezon = "UTC"\n', 'неизвестные ключи'),
    ('[report]\ntimezone = 3\n', 'строкой'),
    ('[compare]\ntolerance_pct = -5\n', 'положительным'),
    ('[compare]\ntolerance_pct = "x"\n', 'положительным'),
    ('[compare]\nfoo = 1\n', 'неизвестные ключи'),
    ('[export]\nformats = ["pdf"]\n', 'допустимы'),
    ('[export]\nbar = 1\n', 'неизвестные ключи'),
    ('[report\n', 'Ошибка в конфиге'),
])
def test_invalid_config_is_rejected(tmp_path, text, match):
    with pytest.raises(convert.ReportError, match=match):
        config.load_config(write(tmp_path, text))


def test_exports_are_deduplicated(tmp_path):
    cfg = config.load_config(write(tmp_path, '[export]\nformats = ["csv", "html", "csv"]\n'))
    assert cfg.exports == ['csv', 'html']


def test_find_config_picks_first_folder(tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.mkdir(); b.mkdir()
    (b / 'report.toml').write_text('[report]\n')
    assert config.find_config(a, b) == str(b / 'report.toml')
    assert config.find_config(a, None) is None


def test_load_for_explicit_missing_is_an_error(tmp_path):
    with pytest.raises(convert.ReportError, match='не найден'):
        config.load_for(str(tmp_path / 'no.toml'))


def test_load_for_without_config_returns_none(tmp_path):
    assert config.load_for(None, tmp_path) is None


def test_validator_entry_point(tmp_path, capsys, monkeypatch):
    path = write(tmp_path, '[report]\ntimezone = "UTC"\n')
    monkeypatch.setattr('sys.argv', ['config.py', path])
    import runpy
    runpy.run_path(str(ROOT / 'config.py'), run_name='__main__')
    assert 'OK' in capsys.readouterr().out
