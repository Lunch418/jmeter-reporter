# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private reporting:
**Security -> Report a vulnerability** on https://github.com/Lunch418/jmeter-reporter .
Expect a first answer within 7 days. There is no bounty.

## Supported versions

Only the latest release (2.x) gets fixes. Upgrade before reporting.

## Threat model

- **JTL and XML files are untrusted input.** Labels, response messages and column names
  come from the system under test and can be hostile. The tool defends against: spreadsheet
  formula injection (labels, cells, JTL headers, CSV), terminal escape sequences in console
  output, Rich markup in the TUI, HTML injection in the HTML export, XML DTD/entity tricks
  (`<!DOCTYPE`/`<!ENTITY` are refused), oversized fields (16 MB), more than 16 384 columns,
  more than 10 000 unique labels, negative or absurd numbers (clean exit code 2, not a crash).
- **No network.** No module imports a network library (a test checks this) and the tool holds
  no secrets. Containers run as a non-root user.
- **Paths are chosen by the operator.** Exports and reports are written to a temporary file and
  moved into place, so a symlink at the target is replaced, not followed.

## What ends up in the report

The 'Исходные данные' sheet copies every JTL column, including URLs, `responseMessage` and
`failureMessage`. If these contain tokens or personal data, they will be in the .xlsx (and in
`history/` copies). Use `--no-raw-data` (or `include_raw_data = false`) for reports that leave
your team. `history/` keeps the last `history_keep` copies (30 by default).

## Known limitations

- Memory grows with the number of distinct elapsed values and labels (capped at 10 000 labels).
- XML parsing uses the standard library (`xml.etree`/expat); DTDs are refused before parsing.
- The offline zips are not signed; verify them against `SHA256SUMS` published as a separate
  release asset, and check the build provenance attestation with `gh attestation verify`.
- The SLA verdict only judges what is in the file: add `required_steps` and `min_samples` to
  `[sla]` so a test that died early cannot pass.

## Verifying a release

```
sha256sum -c SHA256SUMS
gh attestation verify jmeter-report-<version>-offline-pyXY.zip --repo Lunch418/jmeter-reporter
```

License: MIT (see LICENSE).
