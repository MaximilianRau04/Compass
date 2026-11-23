#!/usr/bin/env bash
# Server side: deploy the newest commit on main once CI has published its images.
# Run by compass-deploy.timer every few minutes. Does nothing while main is unchanged or while the
# images for the new commit are not in the registry yet (CI still running, or CI failed).
set -euo pipefail

cd "$(dirname "$0")/../.."
# Where CI pushes the images, from the environment or else from .env (like Compose reads it).
REGISTRY="${COMPASS_REGISTRY:-$(sed -n 's/^COMPASS_REGISTRY=//p' .env | tail -n 1)}"
if [[ -z "$REGISTRY" ]]; then
  echo "COMPASS_REGISTRY missing in .env, e.g. ghcr.io/<github user>" >&2
  exit 1
fi
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

# A recreate that broke off (on this small VM a container can take too long to stop) leaves the
# old container renamed to <id>_compass-<service>-1, and every later run fails on that name. Such
# a container is never the live one, so it can go.
remove_leftovers() {
  docker ps -a --format '{{.Names}}' | grep -E '^[0-9a-f]{12}_compass-' \
    | xargs -r docker rm -f >/dev/null || true
}

export COMPASS_VERSION="$target"
"${COMPOSE[@]}" pull --quiet
remove_leftovers
if ! "${COMPOSE[@]}" up -d --no-build --remove-orphans; then
  echo "compose up failed, removing leftover containers and trying once more"
  remove_leftovers
  "${COMPOSE[@]}" up -d --no-build --remove-orphans
fi

# Wait until the API has run migrations and answers /api/health before marking the commit deployed.
ready=0
for _ in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "deploy failed: api did not become healthy after 60s" >&2
  "${COMPOSE[@]}" logs --tail=40 api >&2 || true
  exit 1
fi
echo "$target" >.deployed
"${COMPOSE[@]}" exec -T api python -m app.cli report-status ops:deploy >/dev/null 2>&1 || true

# Drop older Compass images; images still used by a container are skipped.
docker images --format '{{.Repository}}:{{.Tag}}' --filter "reference=$REGISTRY/compass-*" \
  | grep -v -e ":$target\$" -e ':latest$' \
  | xargs -r docker rmi >/dev/null 2>&1 || true
docker image prune -f >/dev/null
echo "deployed ${target:0:7}"
