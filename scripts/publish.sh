#!/usr/bin/env bash
# SECONDARY / fallback publisher (Playwright, separate Chrome profile). Primary path: the Chrome extension in extension/
# (Settings > Data > "Publish waiting"). Run on demand only.
# Usage: scripts/publish.sh [--dry-run] [--max N]
#   --dry-run  fill + read back, never click Upload, release the item (screenshot in ~/.moc-fetcher/failures)
# First time: scripts/publish.sh --login opens https://www.vinted.nl/ in the fetcher profile; log in by hand.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/fetcher/.venv/bin/python"
[ -x "$PY" ] || { echo "no venv: cd fetcher && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2; exit 1; }
CHROME="${FETCHER_CHROME_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [ "${1:-}" = "--login" ]; then
  exec "$CHROME" --remote-debugging-port="${FETCHER_CDP_PORT:-9333}" --user-data-dir="$HOME/.moc-fetcher/profile" \
    --no-first-run "https://www.vinted.nl/"
fi
cd "$ROOT/fetcher" && exec "$PY" -m fetcher.publisher "$@"
