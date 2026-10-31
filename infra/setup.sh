#!/usr/bin/env bash
# First setup, run through "make setup": writes a small .env so that "make up" works right away.
# Asks for the login, creates the database password and leaves every other option at its default.
# .env.example lists all of them. An existing .env is never touched.
set -euo pipefail

cd "$(dirname "$0")/.."
env_file="${COMPASS_ENV_FILE:-.env}"

fail() {
	echo "$1" >&2
	exit 1
}

[ ! -e "$env_file" ] || fail "$env_file already exists, nothing changed. All options: .env.example"
command -v docker >/dev/null || fail "Docker is missing, see https://docs.docker.com/get-docker/"
command -v openssl >/dev/null || fail "openssl is missing"

detected_timezone() {
	if [ -f /etc/timezone ]; then
		cat /etc/timezone
	elif [ -L /etc/localtime ]; then
		readlink /etc/localtime | sed -n 's|.*zoneinfo/||p'
	fi
}

read -rp "Login name [admin]: " login
login="${login:-admin}"
[[ "$login" =~ ^[A-Za-z0-9._@-]+$ ]] || fail "Use letters, digits and . _ @ - for the login name"

read -rsp "Password: " password
echo
read -rsp "Password again: " again
echo
[ -n "$password" ] || fail "Empty password"
[ "$password" = "$again" ] || fail "The passwords differ"

read -rp "Language of push messages and reviews, en or de [en]: " language
language="${language:-en}"
[[ "$language" =~ ^(en|de)$ ]] || fail "Use en or de"

default_timezone="$(detected_timezone)"
default_timezone="${default_timezone:-Europe/Berlin}"
read -rp "Time zone [$default_timezone]: " timezone
timezone="${timezone:-$default_timezone}"
[[ "$timezone" =~ ^[A-Za-z0-9_+/-]+$ ]] || fail "That is no time zone, e.g. Europe/Berlin"

# Through stdin, so the password does not show up in the process list.
hash="$(printf '%s\n' "$password" | docker run -i --rm caddy:2.10-alpine caddy hash-password)"
[ -n "$hash" ] || fail "Could not hash the password"

umask 077
cat >"$env_file" <<EOF
# Written by make setup. Add more options from .env.example here, then run make up again.
# Calendars and news feeds can also be added in the app, under Settings.

COMPASS_LANGUAGE=$language
TIMEZONE=$timezone

POSTGRES_USER=compass
POSTGRES_PASSWORD=$(openssl rand -hex 24)
POSTGRES_DB=compass

COMPASS_HTTP_PORT=127.0.0.1:8080
COMPASS_BASIC_AUTH_USER=$login
COMPASS_BASIC_AUTH_HASH=${hash//\$/\$\$}

MCP_PUBLIC_URL=http://localhost:8081
EOF

echo "Wrote $env_file. Next: make up, then open http://localhost:8080"
