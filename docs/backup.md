# Backup and restore

Two layers, use both:

| | Covers | Use for |
|---|---|---|
| Settings -> Export JSON/CSV | your stacks only (acquired, notes, tags) | portability, spreadsheets, rebuilding on a fresh catalog |
| `scripts/backup.sh` | whole database (catalog, prices, sales, snapshots, alerts, jobs, card photos) | disaster recovery |

The only copy of the data is the docker volume `moc_mongo_data`. A backup lives on the host, outside it.

## Back up
```bash
scripts/backup.sh                 # -> backups/moc-YYYYmmdd-HHMMSS.archive.gz
scripts/backup.sh --no-catalog    # skip cards + sets (re-importable), ~1/3 the size
scripts/backup.sh --no-photos     # skip card photos (not re-creatable: only for a quick dump)
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
The app container has no docker access, so scheduling is a host launchd job (chosen over cron: it runs at the next wake if the Mac slept).
```bash
scripts/backup_schedule.sh install     # daily 05:30 (before the 06:00 snapshot), keeps newest 14
scripts/backup_schedule.sh status      # loaded?, last exit code, newest archives, log tail
scripts/backup_schedule.sh uninstall
```
Writes `~/Library/LaunchAgents/local.moc.backup.plist`, logs to `~/.moc-backup.log`. Change the time or retention at install: `MOC_BACKUP_HOUR=3 MOC_BACKUP_KEEP=30 scripts/backup_schedule.sh install`. Run once now: `launchctl kickstart gui/$(id -u)/local.moc.backup`. Docker Desktop must be running; the script exits non-zero with a message when the mongo container is down (see the log). Retention is count-based: 14 daily archives = two weeks of history.
