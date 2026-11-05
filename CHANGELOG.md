# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/), versioning: [SemVer](https://semver.org/).
The Excel report is covered by a golden test: it does not change between versions unless noted here.

## [Unreleased]

### Fixed
- Median and percentiles round half UP like JMeter's `Math.round` (Python's `round` is
  banker's: on 5 or 9 samples the median was one element too low).
- Formula injection: labels and response text starting with `= + - @` stay text in Excel
  and get a `'` prefix in CSV exports.
- A broken JTL no longer yields silent zeros: non-numeric `timeStamp`/`elapsed` is an error
  with a line number and a hint about `timestamp_format`; a cut-off last line is skipped with
  a warning; a bad line in the middle is an error.
- Encoding: no more silent replacement characters; non-UTF-8 files give a clear error,
  `JTL_ENCODING=cp1251` reads them.
- SLA with `error_pct` on a JTL without the `success` column is refused instead of failing.

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
