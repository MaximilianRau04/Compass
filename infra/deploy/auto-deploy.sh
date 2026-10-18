#!/usr/bin/env bash
# Server side: deploy the newest commit on main once CI has published its images.
# Run by compass-deploy.timer every few minutes. Does nothing while main is unchanged or while the
# images for the new commit are not in the registry yet (CI still running, or CI failed).
set -euo pipefail

cd "$(dirname "$0")/../.."
REGISTRY="${COMPASS_REGISTRY:-ghcr.io/maximilianrau04}"
BRANCH="${COMPASS_DEPLOY_BRANCH:-main}"
COMPOSE=(docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml)

# One run at a time, a slow pull must not overlap with the next timer tick.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/compass-deploy.lock"
flock -n 9 || exit 0

git fetch --quiet origin "$BRANCH"
target="$(git rev-parse "origin/$BRANCH")"
running="$(cat .deployed 2>/dev/null || true)"
[[ "$target" == "$running" ]] && exit 0

# CI pushes both images tagged with the commit only after tests pass, so their presence is the signal.
for image in compass-api compass-web; do
  if ! docker manifest inspect "$REGISTRY/$image:$target" >/dev/null 2>&1; then
    echo "waiting for $image:${target:0:7} in the registry"
    exit 0
  fi
done

echo "deploying ${target:0:7} (was ${running:0:7})"
git merge --ff-only --quiet "$target"

# A dump right before the new version starts, since the API runs migrations on start.
if "${COMPOSE[@]}" ps --status running --services | grep -qx db; then
  infra/backup/pg-backup.sh
fi

export COMPASS_VERSION="$target"
"${COMPOSE[@]}" pull --quiet
"${COMPOSE[@]}" up -d --no-build --remove-orphans
echo "$target" >.deployed

# Drop older Compass images; images still used by a container are skipped.
docker images --format '{{.Repository}}:{{.Tag}}' --filter "reference=$REGISTRY/compass-*" \
  | grep -v -e ":$target\$" -e ':latest$' \
  | xargs -r docker rmi >/dev/null 2>&1 || true
docker image prune -f >/dev/null
echo "deployed ${target:0:7}"
