# Contributing

## Setup

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
```

Docker alternative: `docker build --target test .`

## Layout

- `convert.py` - JTL parsing and the Excel report (the core; keep it importable without Textual).
- `stats.py`, `sla.py`, `compare.py`, `export.py` - streaming statistics, verdict, comparison, HTML/CSV.
- `config.py`, `minitoml.py` - `report.toml` loading (stdlib fallback parser).
- `cli.py` - `check` / `compare` / `export`; `tui.py`, `preview.py` - interface.
- `tools/` - sample generator, screenshot, offline bundle, changelog helper.

## Rules

- Tests for every change; `tests/test_report_unchanged.py` is a golden test of every Excel cell.
  If you change the report on purpose, update the hash and say so in `CHANGELOG.md`.
- Core modules must not import optional packages at top level (see `tests/test_no_dependencies.py`).
- No network access in program code (checked by `tests/test_release.py`).
- ASCII punctuation only in code, docs and commit messages (`->`, `-`, straight quotes).
- Never commit real data: `*.jtl`, `*.xlsx` and Jenkins XML are ignored outside `samples/`.
- TUI tests must not open windows: use Textual's `run_test()` pilot, e2e only in Docker.

## Adding a feature

1. Put the logic in a plain module (no UI imports), add unit tests.
2. Expose it in `cli.py`, then in `tui.py` if it makes sense.
3. If it is a new top-level `.py` file, add it to `RUNTIME_FILES` in `tools/make_offline_bundle.py`.
4. Add a line under `[Unreleased]` in `CHANGELOG.md` and update `README.md`.

## Release

1. Move the `[Unreleased]` notes to a new `## [X.Y.Z] - date` section and bump `version.py`.
2. `git tag vX.Y.Z && git push --tags`.
3. The `release` workflow runs the tests, checks tag == version, builds the offline bundle and
   publishes a GitHub Release with the changelog text.
