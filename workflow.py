"""Everything that goes next to the Excel report: SLA verdict, comparison, HTML/CSV."""
import os

import compare
import convert
import export
import sla
import stats


def extra_paths(output):
    """Names of the side files for a given report path (report.xlsx -> report_compare.xlsx ...)."""
    stem, _ = os.path.splitext(str(output))
    return {'compare': stem + '_compare.xlsx', 'html': stem + '.html', 'csv': stem + '.csv'}


def run_extras(jtl, output, cfg=None, tz=None, steps=convert.DEFAULT_STEP_PATTERN,
               baseline=None, exports=None, tolerance=None):
    """Compute the optional outputs. The Excel report itself is built by convert.py.

    Returns {'verdict': sla.Verdict|None, 'comparison': compare.Comparison|None,
             'files': [paths]}. Raises convert.ReportError on bad input or bad config.
    """
    result = {'verdict': None, 'comparison': None, 'files': []}
    wanted = list(exports) if exports is not None else (list(cfg.exports) if cfg else [])
    sla_cfg = cfg.sla if cfg else None
    if not (sla_cfg or baseline or wanted):
        return result

    paths = extra_paths(output)
    run = stats.load_run(jtl)
    if sla_cfg:
        result['verdict'] = sla.evaluate(run, sla_cfg, steps)
    if baseline:
        base = stats.load_run(baseline)
        tol = tolerance if tolerance is not None else (
            cfg.tolerance_pct if cfg else compare.DEFAULT_TOLERANCE_PCT)
        cmp = compare.compare_runs(base, run, steps, tol)
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
