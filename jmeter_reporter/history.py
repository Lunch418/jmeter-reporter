"""Run history: old reports are archived instead of overwritten, every run is journaled.

Layout next to the report:
    report.xlsx                     - the latest report (path does not change)
    history/report_20261105_101530.xlsx   - previous versions, stamped with their own mtime
    history/journal.jsonl           - one JSON line per run (stdlib only)
"""
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

DEFAULT_KEEP = 30  # archived copies kept per kind of file; older ones are deleted
HISTORY_DIR = 'history'
JOURNAL_NAME = 'journal.jsonl'


def history_dir(output):
    return Path(output).parent / HISTORY_DIR


def archive_existing(output, extra_files=(), copy_output=False):
    """Keep a report (and its side files) that is about to be overwritten in history/.

    Side files are moved: a stale .html next to a new report would mislead. The report
    itself is moved too unless copy_output=True: then it is COPIED and stays at its path,
    so there is no moment when the report path is empty (the new file replaces it atomically).

    Returns the list of archived paths (empty when there was nothing to keep).
    """
    moved = []
    folder = history_dir(output)
    for path in [Path(output), *map(Path, extra_files)]:
        if not path.is_file():
            continue
        stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y%m%d_%H%M%S')
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f'{path.stem}_{stamp}{path.suffix}'
        counter = 1
        while target.exists():
            counter += 1
            target = folder / f'{path.stem}_{stamp}_{counter}{path.suffix}'
        if copy_output and path == Path(output):
            shutil.copy2(str(path), str(target))
        else:
            shutil.move(str(path), str(target))
        moved.append(target)
    return moved


def prune(output, keep=DEFAULT_KEEP):
    """Delete the oldest archived copies beyond `keep` for each kind (report, _compare, html, csv).
    Never raises. Returns the deleted paths."""
    folder = history_dir(output)
    stem = re.escape(Path(output).stem)
    pattern = re.compile(rf'^{stem}(_compare)?_\d{{8}}_\d{{6}}(_\d+)?(\.[A-Za-z]+)$')
    groups = {}
    try:
        for path in folder.iterdir():
            match = pattern.match(path.name)
            if match and path.is_file():
                groups.setdefault((match.group(1), match.group(3)), []).append(path)
    except OSError:
        return []
    deleted = []
    for files in groups.values():
        files.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
                deleted.append(old)
            except OSError:
                pass
    return deleted


def record(output, jtl, info, extras=None, archived=(), keep=DEFAULT_KEEP):
    """Append one run to the journal. Never raises: history must not break a report."""
    verdict = (extras or {}).get('verdict')
    comparison = (extras or {}).get('comparison')
    check = info.get('verification')
    entry = {
        'time': datetime.now().isoformat(timespec='seconds'),
        'jtl': os.path.basename(str(jtl)),
        'report': os.path.basename(str(output)),
        'rows': info.get('rows'),
        'errors': info.get('errors'),
        'duration': info.get('duration'),
        'xml_check': None if check is None else bool(check.get('ok')),
        'sla': None if verdict is None else ('PASS' if verdict.passed else 'FAIL'),
        'regressions': None if comparison is None else comparison.count('regression'),
        'archived': [p.name for p in archived],
    }
    prune(output, keep)
    try:
        folder = history_dir(output)
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / JOURNAL_NAME, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except OSError:
        return None
    return entry


def read(output_or_folder, limit=20):
    """Latest entries, newest last. Broken lines are skipped."""
    path = Path(output_or_folder)
    folder = path if path.is_dir() else path.parent
    journal = folder / HISTORY_DIR / JOURNAL_NAME
    if not journal.is_file():
        return []
    entries = []
    with open(journal, encoding='utf-8') as handle:
        for line in handle:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    return entries[-limit:]


def format_entry(entry):
    """One readable line: '05.11 10:15  run.jtl  405000 выб., ошибок 3, SLA PASS'."""
    try:
        when = datetime.fromisoformat(entry['time']).strftime('%d.%m %H:%M')
    except (KeyError, ValueError):
        when = '?'
    parts = [f"{entry.get('rows', '?')} выб.", f"ошибок {entry.get('errors', '?')}"]
    if entry.get('sla'):
        parts.append(f"SLA {entry['sla']}")
    if entry.get('regressions') is not None:
        parts.append(f"хуже {entry['regressions']}")
    if entry.get('xml_check') is False:
        parts.append('XML: расхождения')
    return f"{when}  {entry.get('jtl', '?')}  " + ', '.join(parts)
