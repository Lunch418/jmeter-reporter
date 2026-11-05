#!/usr/bin/env bash
# Run the terminal UI in Docker on any folder of this machine.
#   ./report.sh                  # current folder
#   ./report.sh ~/Downloads      # any other folder
#   ./report.sh ~/Downloads convert /data/jmeter.jtl /data/report.xlsx
set -euo pipefail

dir="${1:-$PWD}"
[ "$#" -gt 0 ] && shift
if [ ! -d "$dir" ]; then
  echo "Folder not found: $dir" >&2
  exit 1
fi
dir="$(cd "$dir" && pwd)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# JMETER_REPORT_IMAGE=ghcr.io/lunch418/jenkins ./report.sh  -> use the published image
image="${JMETER_REPORT_IMAGE:-jmeter-report}"
if [ -z "${JMETER_REPORT_IMAGE:-}" ] && ! docker image inspect jmeter-report >/dev/null 2>&1; then
  docker build --target runtime -t jmeter-report "$here"
fi

exec docker run --rm -it \
  --user "$(id -u):$(id -g)" \
  -e TZ="${TZ:-$(cat /etc/timezone 2>/dev/null || echo UTC)}" \
  -v "$dir:/data" \
  "$image" "${@:-tui}"
