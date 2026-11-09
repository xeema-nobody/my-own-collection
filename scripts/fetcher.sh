#!/usr/bin/env bash
# Start/stop the host price fetcher (real Chrome over CDP) on 127.0.0.1:8110.
# Usage: scripts/fetcher.sh [start|stop|restart|status|logs]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$HOME/.moc-fetcher"
PIDFILE="$STATE/fetcher.pid"
LOG="$STATE/fetcher.log"
URL="http://127.0.0.1:${FETCHER_PORT:-8110}"
mkdir -p "$STATE"

healthy() { curl -fsS -m 2 "$URL/health" >/dev/null 2>&1; }

case "${1:-start}" in
  start)
    if healthy; then echo "fetcher already up at $URL"; exit 0; fi
    PY="$ROOT/fetcher/.venv/bin/python"
    if [ ! -x "$PY" ]; then
      echo "no venv: cd fetcher && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2; exit 1
    fi
    CHROME="${FETCHER_CHROME_PATH:-/Applications/Google Chrome.app}"
    [ -e "$CHROME" ] || [ -n "${FETCHER_CHROME_PATH:-}" ] || { echo "Google Chrome not found in /Applications" >&2; exit 1; }
    (cd "$ROOT/fetcher" && nohup "$PY" -m fetcher >>"$LOG" 2>&1 & echo $! >"$PIDFILE")
    for _ in $(seq 1 20); do healthy && { echo "fetcher up at $URL (log: $LOG)"; exit 0; }; sleep 0.5; done
    echo "fetcher did not become healthy; see $LOG" >&2; exit 1 ;;
  stop)
    PID=""
    [ -f "$PIDFILE" ] && PID="$(cat "$PIDFILE")"
    # pidfile lost (old start, reboot): fall back to whatever listens on the fetcher port
    { [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; } || PID="$(lsof -nP -iTCP:"${FETCHER_PORT:-8110}" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
    if [ -n "$PID" ] && kill "$PID" 2>/dev/null; then echo stopped; else echo "not running"; fi
    rm -f "$PIDFILE" ;;
  restart) "$0" stop; for _ in $(seq 1 40); do healthy || break; sleep 0.25; done; exec "$0" start ;;
  status)
    if healthy; then echo "up: $(curl -fsS -m 2 "$URL/status")"; else echo "down"; exit 1; fi ;;
  logs) tail -n 50 "$LOG" ;;
  *) echo "usage: $0 [start|stop|restart|status|logs]" >&2; exit 2 ;;
esac
