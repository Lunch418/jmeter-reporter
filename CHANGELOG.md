# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/), versioning: [SemVer](https://semver.org/).
The Excel report is covered by a golden test: it does not change between versions unless noted here.

## [Unreleased]

### Breaking
- Python 3.10 or newer is required (3.8 and 3.9 are dropped; the fixed-offset fallback table
  for Russian time zones is gone, named zones use the system zoneinfo database).
- Names that `convert.py` used to re-export (`ReportError`, `to_int`, `percentile`,
  `resolve_timezone`, ...) now live in their own modules (`errors`, `jtl`, `stats`,
  `timeutil`, `safety`). The old names still work, raise `DeprecationWarning` and will be
  removed in 2.0.
- The 1.2.0 move into the `jmeter_reporter` package changed import paths; it should have been
  announced as breaking.

### Added
- `samples/jmeter-5.6.3/`: a reference run from a real JMeter 5.6.3 (odd sample counts) with
  expected values produced by JMeter's own `StatCalculator` and its HTML dashboard;
  `tests/test_jmeter_reference.py` checks all numbers against it. (The dashboard computes
  p90/p95/p99 with interpolation, a different method from the Aggregate Report, so those
  are checked against `StatCalculator` only.)

### Changed
- The 'raw data' sheet is streamed straight into the .xlsx archive: 405 000 rows take about
  34 MB of memory instead of several GB. Cells look and read the same (golden test).
- The report is written to a temporary file and moved into place at the end: a failed build
  keeps the previous report, and the old version goes to `history/` only after success.
- `cli.py` returns exit code 2 for unreadable files and CSV errors (was 1 or a traceback).

## [1.2.0] - 2026-11-05

### Fixed
- Median and percentiles round half UP like JMeter's `Math.round` (Python's `round` is
  banker's: on 5 or 9 samples the median was one element too low). Reports of runs with such
  sample counts change; the numbers now match JMeter.
- Formula injection: labels and response text starting with `= + - @` stay text in Excel
  and get a `'` prefix in CSV exports.
- A broken JTL no longer yields silent zeros: non-numeric `timeStamp`/`elapsed` is an error
  with a line number and a hint about `timestamp_format`; a cut-off last line is skipped with
  a warning; a bad line in the middle is an error.
- Encoding: no more silent replacement characters; non-UTF-8 files give a clear error,
  `JTL_ENCODING=cp1251` reads them.
- SLA with `error_pct` on a JTL without the `success` column is refused instead of failing.
- HTML summary shows the exact error count instead of one recomputed from a percentage.

### Changed
- Code moved into the `jmeter_reporter` package (`python convert.py` etc. work as before;
  `pip install .` now provides `jmeter-report`, `jmeter-report-cli`, `jmeter-report-tui`).
- One statistics engine (`stats.py`) for the report, SLA, comparison and exports; it keeps a
  histogram per label instead of every sample (memory depends on distinct values, not rows).
  The raw-data pass streams the file instead of holding a list of rows.
- `convert.py` returns exit code 2 on input errors (like `cli.py`); library code no longer
  calls `sys.exit`.
- Comparison ignores noise: `min_abs_delta_ms` (default 10) and `min_samples` (default 5).
- Docker image: runs as a non-root user (use `--user "$(id -u):$(id -g)"`), base image pinned
  by digest, dependencies installed from `requirements.lock` with hashes.
- CI: actions pinned by SHA, read-only token, Python 3.9/3.12/3.13 plus a core-only 3.8 job,
  coverage gate 90%, Dependabot.

### Added
- Property-based tests (hypothesis) for the formulas; tests for malformed JTL files.

## [1.1.0] - 2026-11-05

### Added
- Run history: a report that is about to be overwritten moves to `history/` with its own
  timestamp, every run is appended to `history/journal.jsonl`. TUI: Ctrl+J shows recent runs.
  `keep_history = false` in `report.toml` turns it off.

## [1.0.0] - 2026-11-05

### Added
- Textual TUI: file tree, preview, options, Ctrl+key shortcuts.
- Cross-check of the JTL against the Jenkins XML files (standardResults, dashBoard).
- `cli.py check` - SLA verdict from `report.toml` with exit codes 0/1/2.
- `cli.py compare` - comparison of two runs (xlsx, CSV fallback).
- `cli.py export` - standalone HTML and CSV summaries.
- `report.toml` configuration (`[report]`, `[compare]`, `[export]`, `[sla]`).
- `--no-raw-data` / `include_raw_data = false` - skip the raw-data sheet for huge runs.
- Docker image, `docker-compose.yml`, `report.sh`.
- Isolated-contour mode: stdlib-only commands, `minitoml.py`, offline bundle
  (`tools/make_offline_bundle.py`), Python 3.8 support for the core, `docs/OFFLINE.md`.
- Dependencies split: `requirements.txt` (core), `requirements-tui.txt`, `requirements-dev.txt`.

### Changed
- Streaming statistics for comparison and checks (about 10x less memory on 400k rows).
