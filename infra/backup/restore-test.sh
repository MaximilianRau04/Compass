#!/usr/bin/env bash
# Restore a dump into a throwaway database on the server and run basic checks.
# Usage: infra/backup/restore-test.sh /var/backups/compass/compass_<stamp>.dump
set -euo pipefail

dump="${1:?path to a compass_*.dump file}"
cd "$(dirname "$0")/../.."
COMPOSE=(docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml)
psql() { "${COMPOSE[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -v ON_ERROR_STOP=1 $*"; }

psql "-d postgres -c 'DROP DATABASE IF EXISTS restore_test' -c 'CREATE DATABASE restore_test'"
"${COMPOSE[@]}" exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d restore_test --no-owner' <"$dump"
psql "-d restore_test -tAc 'SELECT version_num FROM alembic_version'"
psql "-d restore_test -tAc \"SELECT 'tasks=' || (SELECT count(*) FROM tasks) || ' notes=' || (SELECT count(*) FROM notes) || ' health_records=' || (SELECT count(*) FROM health_records)\""
psql "-d postgres -c 'DROP DATABASE restore_test'"
echo "restore test ok"
