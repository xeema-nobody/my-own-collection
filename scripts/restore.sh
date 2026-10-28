#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh.
# Usage: scripts/restore.sh <archive> [--yes]       overwrite the live database (asks first)
#        scripts/restore.sh <archive> --to-scratch  restore into <db>_verify, compare counts, drop it
# Env: MOC_DB (default owncollection), MOC_COMPOSE_SERVICE (default mongo).
# Never touches the docker volume itself (no `down -v`).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DB="${MOC_DB:-owncollection}"
SVC="${MOC_COMPOSE_SERVICE:-mongo}"
FILE="${1:-}"; MODE="${2:-}"
[ -f "$FILE" ] || { echo "usage: $0 <archive> [--yes|--to-scratch]" >&2; exit 2; }

# shellcheck disable=SC2016  # $VARS expand inside the container, on purpose
AUTH='--username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin'
mx() { docker compose exec -T "$SVC" sh -c "$1"; }
counts() {  # "<collection> <count>" lines for database $1
  mx "mongosh --quiet $AUTH --eval 'const d=db.getSiblingDB(\"$1\"); d.getCollectionNames().sort().forEach(c=>print(c, d[c].countDocuments({})))'"
}

if [ "$MODE" = "--to-scratch" ]; then
  V="${DB}_verify"
  mx "mongorestore --quiet $AUTH --archive --gzip --drop --nsInclude '$DB.*' --nsFrom '$DB.*' --nsTo '$V.*'" < "$FILE"
  TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
  counts "$V" </dev/null > "$TMP"
  mx "mongosh --quiet $AUTH --eval 'db.getSiblingDB(\"$V\").dropDatabase()'" </dev/null >/dev/null
  echo "scratch copy in $V (dropped). Collection counts in archive vs live:"
  rc=0; LIVE="$(counts "$DB" </dev/null)"
  while read -r c n; do
    live=$(awk -v c="$c" '$1==c{print $2}' <<<"$LIVE")
    if [ "$n" = "${live:-0}" ]; then echo "  ok    $c $n"; else echo "  DIFF  $c archive=$n live=${live:-0}"; rc=1; fi
  done < "$TMP"
  exit $rc
fi

echo "Restore $FILE -> database '$DB' (service $SVC). Current data in '$DB' will be REPLACED."
echo "Tip: run scripts/backup.sh first."
if [ "$MODE" != "--yes" ]; then
  read -r -p "Type 'restore' to continue: " ans
  [ "$ans" = "restore" ] || { echo aborted; exit 1; }
fi
mx "mongorestore --quiet $AUTH --archive --gzip --drop --nsInclude '$DB.*'" < "$FILE"
echo "restored. Restart the app: docker compose restart app"
