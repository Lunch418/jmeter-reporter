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

- `convert.py`, `cli.py`, `tui.py` in the root are thin launchers; the code is in `jmeter_reporter/`.
- `stats.py` - the ONLY place where numbers are computed (histograms, JMeter formulas).
  `jtl.py` - strict JTL reading. `convert.py` - the Excel report and its CLI.
- `sla.py`, `compare.py`, `export.py`, `history.py`, `workflow.py` - features on top of `stats.Run`.
- `config.py`, `minitoml.py` - `report.toml`; `errors.py`, `timeutil.py`, `safety.py` - small shared parts.
- `tui.py`, `preview.py` - the interface (Textual is optional).
- `tools/` - sample generator, screenshot, offline bundle, changelog helper.

## Rules

- Tests for every change; `tests/test_report_unchanged.py` is a golden test of every Excel cell.
  If you change the report on purpose, update the hash and say so in `CHANGELOG.md`.
- Numbers are computed in `stats.py` only; do not add a second implementation of a formula.
  `tests/test_formulas.py` checks it against the Java algorithm of JMeter's StatCalculator.
- Core modules must not import optional packages at top level (see `tests/test_no_dependencies.py`).
- No network access in program code (checked by `tests/test_release.py`).
- ASCII punctuation only in code, docs and commit messages (`->`, `-`, straight quotes).
- Never commit real data: `*.jtl`, `*.xlsx` and Jenkins XML are ignored outside `samples/`.
- TUI tests must not open windows: use Textual's `run_test()` pilot, e2e only in Docker.

## Adding a feature

1. Put the logic in a plain module (no UI imports), add unit tests.
2. Expose it in `cli.py`, then in `tui.py` if it makes sense.
3. New modules go into `jmeter_reporter/` (the offline bundle picks up the whole folder). A new
   root launcher must be added to `RUNTIME_FILES` and `LAUNCHERS` (`tests/test_release.py`).
4. Add a line under `[Unreleased]` in `CHANGELOG.md` and update `README.md`.

## Dependencies

`requirements*.txt` have loose lower bounds (for people). The Docker image installs the exact,
hashed `requirements.lock`. After changing `requirements.in`:
`pip-compile --generate-hashes --strip-extras requirements.in -o requirements.lock`.
GitHub Actions are pinned by commit SHA; Dependabot proposes updates weekly.

## Release

1. Move the `[Unreleased]` notes to a new `## [X.Y.Z] - date` section and bump `jmeter_reporter/version.py`.
2. `git tag vX.Y.Z && git push --tags`.
3. The `release` workflow runs the tests, checks tag == version, builds the offline bundle and
   publishes a GitHub Release with the changelog text.
