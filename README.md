# JMeter -> Excel report

Turns JMeter load test results (a `.jtl` file in CSV format, for example a
Jenkins build artifact) into an Excel report with a summary table, a response
time chart and the raw data.

Two ways to use it: a **terminal UI** (pick files with the keyboard) and a
plain **command line**.

## Install

Python 3.9+ is required.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Terminal UI

```bash
python3 tui.py                   # starts in the current directory
python3 tui.py ~/Downloads       # or in any other directory
```

- left: file tree, filtered by type (`.jtl/.csv` or all files); hidden files are not shown
- right: input file, output `.xlsx`, time zone (list or custom), regex for chart steps
- `Ctrl+R` or the button builds the report, `Ctrl+Q` quits, `Tab` moves between fields
- the result (samples, errors, start/end time, duration) is shown in the log at the bottom

## Command line

```bash
python3 convert.py jmeter.jtl report.xlsx
python3 convert.py jmeter.jtl report.xlsx --tz Europe/Moscow
python3 convert.py jmeter.jtl report.xlsx --steps '^0[1-5]\.'
```

The old four-argument form
`convert.py jmeter.jtl dashBoard_jmeter.xml standardResults.xml report.xlsx`
still works, but the two XML files are ignored: every number is computed from the JTL.

| Option | Meaning |
|--------|---------|
| `--tz ZONE` | Time zone for timestamps: `local` (default), `UTC`, `Europe/Moscow`, `+05:00` |
| `--steps REGEX` | Which labels go to the chart sheet. Default `^\d{2}\.` (labels like `01. Login`) |

## Getting the input file from Jenkins

Open the build -> Artifacts -> download the `.jtl` file (for example
`jmeter (1).jtl`). The JTL must be CSV: set
`jmeter.save.saveservice.output_format=csv` in JMeter. Required columns:
`timeStamp`, `elapsed`, `label`; `success` is needed for the error rate.

## Report layout

1. **Summary** - start/end time, duration, and per label: samples, average, median,
   90/95/99% lines, min, max, error %, throughput, received/sent KB/s, plus a TOTAL row.
   Statistics follow JMeter's own formulas (percentile index `round(n*p)-1`,
   integer average), so the numbers match the JMeter dashboard.
2. **Time chart** - table and horizontal bar chart (Average and 90% Line) for the steps
   selected by `--steps`.
3. **Raw data** - the full JTL (cut at the Excel row limit, with a warning).

## Sample data and tests

The repository contains only **synthetic** data: `samples/jmeter.jtl` is produced by
`tools/make_sample.py` (fake host `example.test`, seeded random numbers).

```bash
python3 tools/make_sample.py samples/jmeter.jtl      # regenerate the sample
python3 convert.py samples/jmeter.jtl demo.xlsx --tz UTC

pip install -r requirements-dev.txt
python3 -m pytest -q --cov=convert --cov=tui --cov=tools
```

Do not commit real test runs: `.gitignore` blocks `*.jtl`, `*.xlsx` and Jenkins XML
files everywhere except `samples/`.

## Troubleshooting

- `ModuleNotFoundError: openpyxl` / `textual` - run `pip install -r requirements.txt`
  (inside the virtual environment).
- "file looks like XML" - the JTL was saved as XML; switch JMeter to CSV output.
- Wrong times - pass `--tz` (or choose the zone in the UI); the default is the local
  time of the machine running the script.
