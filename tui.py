"""Launcher: python tui.py [folder] (the code lives in the jmeter_reporter package)."""
import sys

try:
    from jmeter_reporter.tui import main
except ImportError as exc:  # only the optional UI packages; anything else is a real bug
    if (exc.name or '').split('.')[0] not in ('textual', 'rich'):
        raise
    sys.exit("Для интерфейса нужен пакет textual: pip install -r requirements-tui.txt\n"
             "Без него работают convert.py и cli.py (консольный режим).")

if __name__ == '__main__':
    main()
