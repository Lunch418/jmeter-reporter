#!/bin/sh
# Entry point of the image: "tui" (default), "convert ...", "sample", or any other command.
set -e
cmd="${1:-tui}"
[ "$#" -gt 0 ] && shift
case "$cmd" in
  tui)     exec python /app/tui.py "${1:-/data}" ;;
  convert) exec python /app/convert.py "$@" ;;
  sample)  exec python /app/tools/make_sample.py "${1:-/data/jmeter.jtl}" ;;
  *)       exec "$cmd" "$@" ;;
esac
