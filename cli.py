"""Launcher: python cli.py ... (the code lives in the jmeter_reporter package)."""
import sys

from jmeter_reporter.cli import main

if __name__ == '__main__':
    sys.exit(main())
