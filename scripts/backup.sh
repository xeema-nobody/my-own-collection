#!/usr/bin/env bash
# Dump the collection database to a gzip archive on the host.
# Usage: scripts/backup.sh [--no-catalog] [dir]
#   dir               target folder (default: $MOC_BACKUP_DIR or ./backups)
#   --no-catalog      skip cards + sets (re-importable); much smaller
# Env: MOC_BACKUP_KEEP (default 14) newest archives kept, MOC_DB (default owncollection),
#      MOC_COMPOSE_SERVICE (default mongo).
# Credentials come from the mongo container's own env; .env is never read here.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DB="${MOC_DB:-owncollection}"
SVC="${MOC_COMPOSE_SERVICE:-mongo}"
KEEP="${MOC_BACKUP_KEEP:-14}"
DIR="${MOC_BACKUP_DIR:-$ROOT/backups}"
EXCLUDE=""
for a in "$@"; do
  case "$a" in
    --no-catalog) EXCLUDE="--excludeCollection=cards --excludeCollection=sets" ;;
    -*) echo "unknown option $a" >&2; exit 2 ;;
    *) DIR="$a" ;;
  esac
done
mkdir -p "$DIR"
OUT="$DIR/moc-$(date +%Y%m%d-%H%M%S).archive.gz"
trap 'rm -f "$OUT.part"' EXIT

# shellcheck disable=SC2016  # $VARS expand inside the container, on purpose
docker compose exec -T "$SVC" sh -c 'mongodump --quiet --username "$MONGO_INITDB_ROOT_USERNAME" \
  --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db '"$DB $EXCLUDE"' \
  --archive --gzip' > "$OUT.part"

[ -s "$OUT.part" ] || { echo "backup is empty" >&2; exit 1; }
# (not a plain .gz: mongodump gzips inside its archive; verify with scripts/restore.sh <file> --to-scratch)
mv "$OUT.part" "$OUT"
echo "backup: $OUT ($(du -h "$OUT" | cut -f1))"

# retention: only our own pattern, newest $KEEP stay
ls -1t "$DIR"/moc-*.archive.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f -- "$old" && echo "pruned: $old"
done
