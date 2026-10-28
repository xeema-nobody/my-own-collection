# Backup and restore

Two layers, use both:

| | Covers | Use for |
|---|---|---|
| Settings -> Export JSON/CSV | your stacks only (acquired, notes, tags) | portability, spreadsheets, rebuilding on a fresh catalog |
| `scripts/backup.sh` | whole database (catalog, prices, sales, snapshots, alerts, jobs) | disaster recovery |

The only copy of the data is the docker volume `moc_mongo_data`. A backup lives on the host, outside it.

## Back up
```bash
scripts/backup.sh                 # -> backups/moc-YYYYmmdd-HHMMSS.archive.gz
scripts/backup.sh --no-catalog    # skip cards + sets (re-importable), ~1/3 the size
scripts/backup.sh /some/folder    # or MOC_BACKUP_DIR=...
```
Newest `MOC_BACKUP_KEEP` (default 14) `moc-*.archive.gz` files stay; older ones are pruned. Nothing else in the folder is touched. `backups/` is gitignored. Credentials come from the mongo container's environment; the script never reads `.env`.

## Verify (do this occasionally)
```bash
scripts/restore.sh backups/<file> --to-scratch
```
Restores into `owncollection_verify`, compares per-collection counts with the live database, drops the scratch copy. Exit code 1 if any count differs (a backup older than recent writes will differ; that is expected).

## Restore
```bash
scripts/backup.sh                         # safety copy of the current state first
scripts/restore.sh backups/<file>         # asks you to type 'restore'; --yes skips the prompt
docker compose restart app
```
Replaces the collections contained in the archive (`--drop`); collections not in the archive (e.g. `cards` after a `--no-catalog` backup) are left alone. Never `docker compose down -v`: it deletes the volume.

## Schedule (host, Mac must be awake)
The app container has no docker access, so scheduling is a host job. Daily 05:30 (before the 06:00 snapshot):
```cron
30 5 * * * cd /Users/xeema/xeema/projects/nobody/my-own-collection && scripts/backup.sh >> ~/.moc-backup.log 2>&1
```
or launchd (`~/Library/LaunchAgents/local.moc.backup.plist`, then `launchctl load` it; runs at next wake if the Mac was asleep):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.moc.backup</string>
  <key>ProgramArguments</key><array><string>/Users/xeema/xeema/projects/nobody/my-own-collection/scripts/backup.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>5</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>/Users/xeema/.moc-backup.log</string>
  <key>StandardErrorPath</key><string>/Users/xeema/.moc-backup.log</string>
</dict></plist>
```
Docker Desktop must be running; the script exits non-zero with a message when the mongo container is down.
