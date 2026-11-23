#!/usr/bin/env bash
# Server side: nightly pg_dump of the Compass database into $COMPASS_BACKUP_DIR.
# Keeps the last $COMPASS_BACKUP_KEEP_DAYS days; the PC pulls these files (pull-backup.sh).
set -euo pipefail
umask 077

cd "$(dirname "$0")/../.."
BACKUP_DIR="${COMPASS_BACKUP_DIR:-/var/backups/compass}"
KEEP_DAYS="${COMPASS_BACKUP_KEEP_DAYS:-14}"
COMPOSE=(docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml)

mkdir -p "$BACKUP_DIR"
stamp="$(date +%F_%H%M)"
partial="$BACKUP_DIR/.compass_$stamp.dump.partial"

"${COMPOSE[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' >"$partial"
if [[ ! -s "$partial" ]]; then
  rm -f "$partial"
  echo "pg_dump produced an empty file" >&2
  exit 1
fi
mv "$partial" "$BACKUP_DIR/compass_$stamp.dump"

find "$BACKUP_DIR" -name 'compass_*.dump' -mtime +"$KEEP_DAYS" -delete
"${COMPOSE[@]}" exec -T api python -m app.cli report-status ops:backup >/dev/null 2>&1 || true
echo "backup written: $BACKUP_DIR/compass_$stamp.dump"
