# Work in an isolated contour (no internet)

The program never touches the network: no telemetry, no update checks, no downloads at run time.
The only thing that needs internet is the one-time delivery of Python packages, and even that
can be skipped.

## What works with nothing but Python

| Command | Needs |
|---|---|
| `python cli.py check run.jtl` (SLA verdict, exit codes 0/1/2) | Python 3.10+ only |
| `python cli.py export run.jtl --format html` or `csv` | Python 3.10+ only |
| `python cli.py compare base.jtl new.jtl` | Python 3.10+ only (writes CSV) |
| `python convert.py run.jtl` (Excel report) | + `openpyxl` |
| `python tui.py` (interactive UI) | + `textual` (Python 3.10+) |

`report.toml` is read with `tomllib` (3.11+), `tomli` or the built-in `minitoml.py`, whichever
exists, so no TOML package is required.

Time zones: `UTC` and fixed offsets (`+03:00`) always work. Named zones (`Europe/Moscow`) need
the system time zone database (on Windows the `tzdata` package).

## Route 1 - wheel bundle (recommended)

On a machine with internet (any Python; the target version is given with `--python-version`):

```
python tools/make_offline_bundle.py --with-tui --python-version 3.10
```

A bundle fits ONE Python version: wheel versions differ (for example `platformdirs` needs 3.11+).
GitHub Releases carry one zip per version: `-py310`, `-py311`, `-py312`, `-py313`. Take the one
that matches `python3 --version` in the contour.

Copy `dist/jmeter-report-<version>-offline-pyXY.zip` into the contour (through the approved media
channel), unpack, then:

```
(cd wheels && sha256sum -c SHA256SUMS)
python3 -m venv .venv
. .venv/bin/activate
pip install --no-index --find-links wheels -r requirements-tui.txt
python convert.py --version
```

`--no-index` guarantees pip does not try to reach PyPI.

## Route 2 - Docker image

On a machine with internet:

```
docker build -t jmeter-report .
docker save jmeter-report | gzip > jmeter-report.tar.gz
```

In the contour:

```
gunzip -c jmeter-report.tar.gz | docker load
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/data" jmeter-report convert /data/run.jtl
```

## Route 3 - no packages at all

Copy the `jmeter_reporter/` folder and the three launchers (`cli.py`, `convert.py`, `tui.py`) and use only the stdlib commands from the table above. The Excel report
is the one thing you give up; use `export --format html` instead.

## Supported Python versions

Python 3.10 - 3.13. Astra Linux 1.7 ships Python 3.7: not supported, install a newer
Python or use the Docker route.

## Audit notes

- No network modules are imported by any program file (checked by `tests/test_release.py`).
- No real data is bundled; `samples/` is synthetic.
- Every wheel in the bundle is listed with its SHA-256 in `wheels/SHA256SUMS`.
