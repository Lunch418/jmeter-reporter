# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/), versioning: [SemVer](https://semver.org/).
The Excel report is covered by a golden test: it does not change between versions unless noted here.

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
