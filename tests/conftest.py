import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / 'tools'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


@pytest.fixture
def sample_jtl(tmp_path):
    """Небольшой детерминированный JTL, сгенерированный на лету."""
    import make_sample
    path = tmp_path / 'sample.jtl'
    make_sample.write_jtl(path, iterations=6, seed=1)
    return path


@pytest.fixture
def sample_xml(sample_jtl, tmp_path):
    """standardResults.xml и dashBoard_jmeter.xml, согласованные с sample_jtl."""
    import make_sample
    std, dash = tmp_path / 'standardResults.xml', tmp_path / 'dashBoard_jmeter.xml'
    make_sample.write_xml(sample_jtl, std, dash)
    return std, dash


@pytest.fixture
def slow_jtl(tmp_path):
    """Второй прогон (другой seed): немного другие цифры, для сравнения."""
    import make_sample
    path = tmp_path / 'slow.jtl'
    make_sample.write_jtl(path, iterations=6, seed=9)
    return path


@pytest.fixture
def make_run(tmp_path):
    """Фабрика: JTL из списка (label, elapsed, success) -> stats.Run."""
    import stats

    def build(samples, name='run.jtl'):
        path = tmp_path / name
        lines = ['timeStamp,elapsed,label,success']
        for i, (label, elapsed, ok) in enumerate(samples):
            lines.append(f'{1768471200000 + i * 1000},{elapsed},{label},{"true" if ok else "false"}')
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return stats.load_run(path)

    return build
