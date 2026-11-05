import csv

import make_sample


def test_generator_is_deterministic(tmp_path):
    a, b = tmp_path / 'a.jtl', tmp_path / 'b.jtl'
    make_sample.write_jtl(a, iterations=3, seed=5)
    make_sample.write_jtl(b, iterations=3, seed=5)
    assert a.read_bytes() == b.read_bytes()


def test_generator_output_shape(tmp_path):
    path = tmp_path / 'g.jtl'
    make_sample.write_jtl(path, iterations=2, seed=1)
    rows = list(csv.DictReader(open(path, encoding='utf-8')))
    assert list(rows[0].keys()) == make_sample.HEADER
    labels = {r['label'] for r in rows}
    assert all(f'{n:02d}. ' in ' '.join(labels) for n in range(1, 11))


def test_generator_contains_no_real_hosts(tmp_path):
    path = tmp_path / 'g.jtl'
    make_sample.write_jtl(path, iterations=2)
    text = path.read_text(encoding='utf-8')
    assert 'example.test' in text and '.ru' not in text


def test_committed_sample_matches_generator(tmp_path):
    from pathlib import Path
    fresh = tmp_path / 'fresh.jtl'
    make_sample.write_jtl(fresh)
    committed = Path(__file__).resolve().parent.parent / 'samples' / 'jmeter.jtl'
    assert committed.read_bytes() == fresh.read_bytes()


def test_committed_xml_samples_match_generator(tmp_path):
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / 'samples'
    std, dash = tmp_path / 'standardResults.xml', tmp_path / 'dashBoard_jmeter.xml'
    make_sample.write_xml(root / 'jmeter.jtl', std, dash)
    assert std.read_bytes() == (root / 'standardResults.xml').read_bytes()
    assert dash.read_bytes() == (root / 'dashBoard_jmeter.xml').read_bytes()
