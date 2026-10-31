#!/usr/bin/env bash
# PC side: pull the dumps from the server over the VPN and snapshot them with restic.
# Configure via ~/.config/compass/backup.env (see docs/deploy.md).
set -euo pipefail
umask 077

: "${COMPASS_SERVER:?set COMPASS_SERVER to the SSH host of the server}"
REMOTE_DIR="${COMPASS_REMOTE_BACKUP_DIR:-/var/backups/compass}"
LOCAL_DIR="${COMPASS_LOCAL_BACKUP_DIR:-$HOME/Backups/compass/dumps}"
export RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-$HOME/Backups/compass/restic}"
export RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-$HOME/.config/compass/restic-password}"

mkdir -p "$LOCAL_DIR"
rsync -a --delete "$COMPASS_SERVER:$REMOTE_DIR/" "$LOCAL_DIR/"

newest="$(find "$LOCAL_DIR" -name 'compass_*.dump' -mtime -2 | head -n1)"
if [[ -z "$newest" ]]; then
  echo "warning: no dump newer than 2 days on the server" >&2
fi

restic backup --tag compass --host compass-server "$LOCAL_DIR"
restic forget --tag compass --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune
