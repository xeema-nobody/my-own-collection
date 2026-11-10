#!/usr/bin/env bash
# Daily host backup via launchd. Usage: scripts/backup_schedule.sh install|uninstall|status
# Runs scripts/backup.sh at 05:30 (before the 06:00 snapshot); launchd runs it at next wake if the Mac slept.
# Env at install time: MOC_BACKUP_HOUR (5), MOC_BACKUP_MINUTE (30), MOC_BACKUP_KEEP (14, written into the plist).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="local.moc.backup"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/.moc-backup.log"
HOUR="${MOC_BACKUP_HOUR:-5}"; MIN="${MOC_BACKUP_MINUTE:-30}"; KEEP="${MOC_BACKUP_KEEP:-14}"
DOMAIN="gui/$(id -u)"

case "${1:-}" in
  install)
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$ROOT/scripts/backup.sh</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>MOC_BACKUP_KEEP</key><string>$KEEP</string>
  </dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MIN</integer></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
EOF
    plutil -lint "$PLIST" >/dev/null
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "installed: daily $(printf '%02d:%02d' "$HOUR" "$MIN"), keep $KEEP, log $LOG"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "uninstalled"
    ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      echo "loaded: $PLIST"
      launchctl print "$DOMAIN/$LABEL" | grep -E "state|last exit code|runs" || true
    else
      echo "not loaded"
    fi
    ls -1t "$ROOT"/backups/moc-*.archive.gz 2>/dev/null | head -3 || true
    [ -f "$LOG" ] && { echo "--- tail $LOG"; tail -5 "$LOG"; } || true
    ;;
  *) echo "usage: $0 install|uninstall|status" >&2; exit 2 ;;
esac
