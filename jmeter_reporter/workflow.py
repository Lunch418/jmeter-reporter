"""Everything that goes next to the Excel report: SLA verdict, comparison, HTML/CSV."""
import os

from . import compare
from . import convert
from . import export
from . import sla
from . import stats


def extra_paths(output):
    """Names of the side files for a given report path (report.xlsx -> report_compare.xlsx ...)."""
    stem, _ = os.path.splitext(str(output))
    return {'compare': stem + '_compare.xlsx', 'html': stem + '.html', 'csv': stem + '.csv'}


def run_extras(jtl, output, cfg=None, tz=None, steps=convert.DEFAULT_STEP_PATTERN,
               baseline=None, exports=None, tolerance=None, run=None):
    """Compute the optional outputs. The Excel report itself is built by convert.py.

    Returns {'verdict': sla.Verdict|None, 'comparison': compare.Comparison|None,
             'files': [paths]}. Raises ReportError on bad input or bad config.
    `run` is an already loaded stats.Run of `jtl` (saves one pass over the file).
    """
    result = {'verdict': None, 'comparison': None, 'files': []}
    wanted = list(exports) if exports is not None else (list(cfg.exports) if cfg else [])
    sla_cfg = cfg.sla if cfg else None
    if not (sla_cfg or baseline or wanted):
        return result

    paths = extra_paths(output)
    if run is None:  # pass the Run from create_excel_report to avoid re-reading a big file
        run = stats.load_run(jtl)
    if sla_cfg:
        result['verdict'] = sla.evaluate(run, sla_cfg, steps)
    if baseline:
        base = stats.load_run(baseline)
        tol = tolerance if tolerance is not None else (
            cfg.tolerance_pct if cfg else compare.DEFAULT_TOLERANCE_PCT)
        cmp = compare.compare_runs(
            base, run, steps, tol,
            min_abs_ms=cfg.min_abs_delta_ms if cfg else compare.DEFAULT_MIN_ABS_MS,
            min_samples=cfg.min_samples if cfg else compare.DEFAULT_MIN_SAMPLES)
        written = compare.write_comparison(cmp, paths['compare'])
        result['comparison'] = cmp
        result['files'].append(written)
    if 'html' in wanted:
        export.write_html(run, paths['html'], tz, steps, result['verdict'])
        result['files'].append(paths['html'])
    if 'csv' in wanted:
        export.write_csv(run, paths['csv'], steps)
        result['files'].append(paths['csv'])
    return result
