#!/usr/bin/env python3
"""Extra commands next to the report builder (convert.py):

    cli.py check   JTL            # SLA verdict from report.toml, exit code 1 on FAIL
    cli.py compare BASE NEW       # what got better / worse between two runs
    cli.py export  JTL --format html csv

Exit codes: 0 - ok, 1 - SLA failed (check) or regressions found (compare --fail-on-regression),
2 - bad input or config.
"""
import argparse
import os
import sys

from . import compare
from . import config
from . import export
from . import sla
from . import stats
from . import workflow
from .errors import ReportError
from .stats import DEFAULT_STEP_PATTERN
from .timeutil import resolve_timezone


def _load_config(args):
    return config.load_for(args.config, os.getcwd())


def _steps(args, cfg):
    return args.steps or (cfg.steps if cfg else None) or DEFAULT_STEP_PATTERN


def _tz(args, cfg):
    return resolve_timezone(args.tz or (cfg.timezone if cfg else None))


def cmd_check(args):
    cfg = _load_config(args)
    if not cfg or not cfg.sla:
        raise ReportError(
            "Нет раздела [sla]: создайте report.toml (пример: report.example.toml) "
            "или укажите --config.")
    run = stats.load_run(args.jtl)
    verdict = sla.evaluate(run, cfg.sla, _steps(args, cfg))
    print(sla.format_verdict(verdict))
    return 0 if verdict.passed else 1


def cmd_compare(args):
    cfg = _load_config(args)
    tolerance = args.tolerance if args.tolerance is not None else (
        cfg.tolerance_pct if cfg else compare.DEFAULT_TOLERANCE_PCT)
    base = stats.load_run(args.base)
    new = stats.load_run(args.new)
    min_abs = args.min_abs_ms if args.min_abs_ms is not None else (
        cfg.min_abs_delta_ms if cfg else compare.DEFAULT_MIN_ABS_MS)
    min_samples = args.min_samples if args.min_samples is not None else (
        cfg.min_samples if cfg else compare.DEFAULT_MIN_SAMPLES)
    cmp = compare.compare_runs(base, new, _steps(args, cfg), tolerance,
                               steps_only=not args.all_labels,
                               min_abs_ms=min_abs, min_samples=min_samples)
    out = args.output or workflow.extra_paths(args.new)['compare']
    written = compare.write_comparison(cmp, out)
    print(compare.format_comparison(cmp))
    if written != out:
        print("openpyxl не установлен: сравнение сохранено как CSV.", file=sys.stderr)
    print(f"Файл: {written}")
    return 1 if (args.fail_on_regression and cmp.has_regressions) else 0


def cmd_export(args):
    cfg = _load_config(args)
    run = stats.load_run(args.jtl)
    steps = _steps(args, cfg)
    verdict = sla.evaluate(run, cfg.sla, steps) if (cfg and cfg.sla) else None
    base_out = args.output or os.path.splitext(args.jtl)[0] + '_report.xlsx'
    paths = workflow.extra_paths(base_out)
    for fmt in args.format:
        # -o names the file itself only for one format with a matching extension
        # (-o my.html); otherwise it is just the base name (-o report.xlsx -> report.html).
        exact = (args.output and len(args.format) == 1
                 and args.output.lower().endswith('.' + fmt))
        target = args.output if exact else paths[fmt]
        if fmt == 'html':
            export.write_html(run, target, _tz(args, cfg), steps, verdict)
        else:
            export.write_csv(run, target, steps)
        print(f"Файл: {target}")
    return 0


EXIT_CODES = (
    "Коды выхода: 0 - все хорошо; 1 - SLA нарушен (check) или найдены ухудшения\n"
    "(compare --fail-on-regression); 2 - ошибка входных данных, файла или конфига;\n"
    "3 - внутренняя ошибка программы (подробности в stderr, пришлите их автору).")


def build_parser():
    from . import version
    parser = argparse.ArgumentParser(
        prog='cli.py', description=__doc__.split('\n\n')[0], epilog=EXIT_CODES,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action='version', version=f'jmeter-report {version.__version__}')
    sub = parser.add_subparsers(dest='command', required=True)

    def common(p):
        p.add_argument('--config', help='report.toml (по умолчанию из текущей папки)')
        p.add_argument('--steps', help='регулярное выражение шагов')

    p = sub.add_parser('check', help='проверить SLA из report.toml')
    p.add_argument('jtl')
    common(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser('compare', help='сравнить два прогона')
    p.add_argument('base', help='базовый JTL (до изменений)')
    p.add_argument('new', help='новый JTL (после изменений)')
    p.add_argument('-o', '--output',
                   help='куда сохранить .xlsx или .csv (по умолчанию .xlsx рядом с новым)')
    p.add_argument('--tolerance', type=float, help='допуск в процентах (по умолчанию 10)')
    p.add_argument('--min-abs-ms', type=float,
                   help='не считать изменением сдвиг меньше стольких мс (по умолчанию 10)')
    p.add_argument('--min-samples', type=int,
                   help='не сравнивать метки, где замеров меньше (по умолчанию 5)')
    p.add_argument('--all-labels', action='store_true', help='сравнивать все метки, не только шаги')
    p.add_argument('--fail-on-regression', action='store_true',
                   help='код выхода 1, если есть ухудшения')
    common(p)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser('export', help='сохранить HTML и/или CSV')
    p.add_argument('jtl')
    p.add_argument('--format', nargs='+', choices=config.EXPORT_FORMATS, default=['html'])
    p.add_argument('-o', '--output',
                   help='имя файла (my.html) или основа имени (report.xlsx -> report.html)')
    p.add_argument('--tz', help='часовой пояс меток времени')
    common(p)
    p.set_defaults(func=cmd_export)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ReportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:  # unreadable / unwritable file: still an input problem, not "FAIL"
        print(f"{exc.strerror or exc}: {getattr(exc, 'filename', '') or ''}".strip(': '),
              file=sys.stderr)
        return 2
    except Exception:  # a bug must not look like "SLA failed" (exit 1) in a CI pipeline
        import traceback
        traceback.print_exc()
        print("Внутренняя ошибка программы (код выхода 3).", file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
