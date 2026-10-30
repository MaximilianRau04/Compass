# Deployment

Compass is meant to run on a small server inside a private network (a VPN such as Tailscale, Headscale or
WireGuard). CI builds the images and pushes them to GHCR. The server only pulls the images, it never
builds them.

```
GitHub Actions --push--> ghcr.io/<owner>/compass-{api,web}
                                   |
                                   v  pull
client --VPN--> reverse proxy (TLS) --HTTP--> Compass Caddy (login) -> API / worker -> Postgres
                                                                   |
                                                                   v  nightly pg_dump
                                            /var/backups/compass  <--rsync over VPN--  PC (restic)
```

The examples below use `compass.example.com` for the dashboard and `mcp.example.com` for the MCP server.
Replace them with your own names.

Compass's own Caddy only listens on localhost: `127.0.0.1:8080` for the dashboard and `127.0.0.1:8081` for
MCP. TLS ends at a reverse proxy in front of it, which you already run or set up for this. That proxy must:

- forward `compass.example.com` to `127.0.0.1:8080` and `mcp.example.com` to `127.0.0.1:8081`, with the
  original `Host` header,
- set `X-Forwarded-For` to the real client address and overwrite whatever the client sent,
- only let VPN clients reach `compass.example.com` (see [Restricting the dashboard](#restricting-the-dashboard)).

## 1. One-time setup on the server

### Prerequisites

You need Docker Engine with the compose plugin, `git` and `make`. When idle, the stack uses a few hundred
MB of RAM.

### Repository (read-only deploy key)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/compass_deploy -N "" -C "compass deploy key"
cat ~/.ssh/compass_deploy.pub
```

Add the public key under GitHub → Compass → Settings → Deploy keys and leave write access off. Then:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github-compass
  HostName github.com
  User git
  IdentityFile ~/.ssh/compass_deploy
  IdentitiesOnly yes
EOF

sudo mkdir -p /opt/compass && sudo chown "$USER": /opt/compass
git clone github-compass:<owner>/Compass.git /opt/compass
```

### Registry login

Create a classic personal access token with **only** the `read:packages` scope:
<https://github.com/settings/tokens/new?scopes=read:packages&description=compass-server>

```bash
docker login ghcr.io -u <github-user>   # paste the token as the password
```

### DNS

Point `compass.example.com` at the server's VPN address. The name may resolve publicly, but on its own
that does not keep the dashboard private, see below.

If the name does not resolve at home, check whether the router has DNS rebinding protection. For example,
a FritzBox blocks public names that point to private IPs. In that case add the name as an exception.

### Configuration

```bash
cd /opt/compass
cp .env.example .env && chmod 600 .env
```

Set these values in `.env`. The IMAP entries can stay empty for now.

| Variable | Value |
|---|---|
| `POSTGRES_PASSWORD` | output of `openssl rand -base64 32 \| tr -d '/+='` |
| `COMPASS_BASIC_AUTH_USER` | your login name |
| `COMPASS_BASIC_AUTH_HASH` | output of `make password-hash` |
| `COMPASS_REGISTRY` | `ghcr.io/<owner>` in lowercase, where CI pushes the images |
| `COMPASS_LANGUAGE` | `en` (default) or `de`: language of push notifications, the weekly review, mail summaries and the MCP prompts |
| `TIMEZONE` | your time zone, default `Europe/Berlin` |

Keep the defaults `COMPASS_HTTP_PORT=127.0.0.1:8080`, `COMPASS_SITE_ADDRESS=:80` and `COMPASS_TLS_MODE=off`.

If there is no proxy in front, Compass's Caddy can terminate TLS itself. Use the domain as
`COMPASS_SITE_ADDRESS` and publish ports 80 and 443 in your own compose override. Then:

- **Server reachable from the internet:** keep `COMPASS_TLS_MODE=off`. With a domain as site address,
  Caddy gets a Let's Encrypt certificate on its own through the HTTP challenge.
- **Server only reachable in the VPN:** Let's Encrypt cannot reach it, so the certificate has to come
  through a DNS challenge. The image has the module for netcup DNS built in: set `COMPASS_TLS_MODE=netcup`
  and fill in the `NETCUP_*` values. For another DNS provider, add its
  [caddy-dns](https://github.com/caddy-dns) module to the `xcaddy build` line in `frontend/Dockerfile` and
  a `(tls-<provider>)` snippet next to `(tls-netcup)` in `infra/caddy/Caddyfile`, then set
  `COMPASS_TLS_MODE=<provider>`.

### Restricting the dashboard

A VPN-only DNS record is not enough if the proxy also accepts connections on a public address: anyone who
connects there with `compass.example.com` as SNI reaches the dashboard, protected only by the basic auth
login. So the proxy has to check the client address for that hostname.

With Caddy as the proxy (2.7 or newer is needed for `trusted_proxies` and `client_ip`; some distributions
ship older versions, so use the [official repository](https://caddyserver.com/docs/install)):

```caddy
{
    servers {
        # Only needed if another proxy sits in front of this one and sets X-Forwarded-For.
        trusted_proxies static <front-proxy-ip>/32
    }
}

http:// {
    @compass host compass.example.com
    handle @compass {
        @outside_vpn not client_ip <vpn-range>
        respond @outside_vpn 403
        reverse_proxy 127.0.0.1:8080
    }

    @mcp host mcp.example.com
    handle @mcp {
        reverse_proxy 127.0.0.1:8081
    }

    handle {
        respond 403
    }
}
```

`<vpn-range>` is the address range of your VPN, for Tailscale and Headscale `100.64.0.0/10`. Two things to
check when the filter blocks VPN clients too:

- A Caddy that listens on IPv6 sees IPv4 peers as `::ffff:a.b.c.d`. Add that spelling to `trusted_proxies`.
- If a proxy in front runs in Docker, VPN clients may arrive with the Docker gateway address instead of
  their VPN address. Then that gateway address is what identifies VPN traffic.

To see what the proxy actually receives, add a temporary route and call it once over the VPN and once
over the public address. Remove it afterwards.

```caddy
    handle /__debug {
        respond "client_ip={client_ip} remote={remote_host} xff={header.X-Forwarded-For}"
    }
```

### Start

```bash
make deploy
curl -s http://127.0.0.1:8080/api/health    # on the server, straight to Compass's Caddy
```

Check from a VPN client:

```bash
curl https://compass.example.com/api/health    # {"status":"ok","database":"ok"}
# through the public address instead of the VPN, must be 403, also with a forged header:
curl -s -o /dev/null -w '%{http_code}\n' --resolve compass.example.com:443:<public-ip> \
  -H 'X-Forwarded-For: <vpn-client-ip>' https://compass.example.com/api/health
```

Then open <https://compass.example.com> in the browser and log in.

## 2. Backups on the server

```bash
sudo mkdir -p /var/backups/compass && sudo chown "$USER": /var/backups/compass
sudo cp infra/backup/systemd/compass-backup.{service,timer} /etc/systemd/system/
sudo sed -i "s/^User=compass/User=$USER/" /etc/systemd/system/compass-backup.service
sudo systemctl daemon-reload
sudo systemctl enable --now compass-backup.timer

sudo systemctl start compass-backup.service   # run once now
ls -l /var/backups/compass
```

Your user must be in the `docker` group, because the service runs as that user.

## 3. Backup pull on the PC

The PC needs key-based SSH to the server without a password prompt, and `restic`. The server's sshd must
allow `PubkeyAuthentication yes`.

```bash
sudo apt install restic

printf '\nHost compass-server\n  HostName <server-vpn-address>\n  User <user>\n' >> ~/.ssh/config
ssh-copy-id compass-server
ssh -o BatchMode=yes compass-server 'echo ok'    # must print ok without asking for a password

mkdir -p ~/.config/compass ~/.local/bin ~/.config/systemd/user
openssl rand -base64 32 > ~/.config/compass/restic-password && chmod 600 ~/.config/compass/restic-password
cat > ~/.config/compass/backup.env <<'EOF'
COMPASS_SERVER=compass-server
EOF
```

To keep the backups somewhere else, e.g. on an external drive, add these lines to `backup.env`. Quote
paths that contain spaces:

```bash
COMPASS_LOCAL_BACKUP_DIR="/media/<user>/<drive>/Backups/compass/dumps"
RESTIC_REPOSITORY="/media/<user>/<drive>/Backups/compass/restic"
```

The examples below use the default `~/Backups/compass/restic`; replace it with your path.

**Store the restic password in your password manager too.** Without it, the backups cannot be read.

```bash
cd <path-to-your-clone>
install -m 755 infra/backup/pull-backup.sh ~/.local/bin/compass-pull-backup
cp infra/backup/systemd/compass-pull-backup.{service,timer} ~/.config/systemd/user/

RESTIC_REPOSITORY=~/Backups/compass/restic RESTIC_PASSWORD_FILE=~/.config/compass/restic-password restic init

systemctl --user daemon-reload
systemctl --user enable --now compass-pull-backup.timer
systemctl --user start compass-pull-backup.service    # run once now
journalctl --user -u compass-pull-backup.service -n 20
```

The timer runs at 09:00, 15:00 and 21:00. If the PC was off, it catches up on the next start.

## 4. Restore test

Do this once after setting up, and again after larger schema changes. Run it on the server:

```bash
cd /opt/compass
infra/backup/restore-test.sh "$(ls -t /var/backups/compass/compass_*.dump | head -1)"
```

The script restores the dump into a temporary database, checks the migration version and drops the
database again.

To restore from the PC after losing the server:

```bash
export RESTIC_REPOSITORY=~/Backups/compass/restic RESTIC_PASSWORD_FILE=~/.config/compass/restic-password
restic snapshots
restic restore latest --target /tmp/compass-restore
# copy a dump to the new server, then:
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml exec -T db \
  sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < compass_<stamp>.dump
```

## 5. MCP server for Claude

The MCP server runs as its own container (`mcp`) behind its own hostname. It is the only part of Compass
that has to be reachable from the internet: Claude calls it from Anthropic's servers, also when you use
the phone app. Claude rejects MCP hosts that resolve to private addresses, so this hostname needs a public
address (unlike the dashboard).

Everything else stays behind the VPN. The proxy forwards the MCP hostname only to `127.0.0.1:8081`, where
Compass's Caddy passes it to the `mcp` container. That container serves `/mcp`, the OAuth endpoints and
the login page, nothing from the dashboard.

Authentication is OAuth with the built-in authorization server: Claude registers itself, opens the
Compass login page in your browser, and you sign in with the same user and password as the
dashboard (`COMPASS_BASIC_AUTH_USER` / `COMPASS_BASIC_AUTH_HASH`). Failed logins are throttled per client
IP, which only works if the proxy passes the real client address in `X-Forwarded-For`.

`.env` on the server:

| Variable | Value |
|---|---|
| `MCP_PUBLIC_URL` | `https://mcp.example.com` |
| `COMPASS_MCP_SITE_ADDRESS` | keep `:8081`. A hostname here would make Caddy try to get its own certificate. |
| `COMPASS_MCP_ALLOWED_IPS` | optional, e.g. `160.79.104.0/21` (Anthropic's outbound range) |

Then run `make deploy` and check from outside the VPN:

```bash
curl https://mcp.example.com/health                                    # {"status":"ok"}
curl https://mcp.example.com/.well-known/oauth-authorization-server    # JSON with issuer https://mcp.example.com
```

### Connect Claude

claude.ai → Settings → Connectors → Add custom connector → URL `https://mcp.example.com/mcp`.
Leave the advanced OAuth fields empty. After the login the connector is also available in the
Claude apps on your phone.

To test locally before deploying, run `make up` and add the server to Claude Code:

```bash
claude mcp add --transport http compass-local http://localhost:8081/mcp
```

Then run `/mcp` in Claude Code and choose "Authenticate"; the login page opens in the browser.

### Revoke access

Every write through MCP is recorded in the `audit_log` table. To log out all clients at once:

```bash
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml exec mcp \
  python -c "from app.mcp.oauth import revoke_all_tokens; print(revoke_all_tokens())"
```

## 6. Calendars and deadlines

Add the subscription URLs to `.env` on the server and run `make deploy` (the worker picks them up on
start and then syncs every `CALENDAR_SYNC_MINUTES`):

| Variable | Value |
|---|---|
| `CALENDAR_ICS_FEEDS` | calendars as `name=url` pairs separated by spaces, e.g. a Google Calendar "secret address in iCal format" |
| `CALENDAR_DEADLINES` | feeds whose matching entries become tasks, as `feed=regex` separated by semicolons |
| `CALENDAR_FEED_AREAS` | area per feed as `feed=area` pairs: colour and filter for its events, and the area of its deadline tasks |
| `ILIAS_ICS_URL` | the subscription link of your ILIAS calendar (calendar → subscribe / export). Its deadlines need no pattern |

A pattern is a regular expression on the entry's title, and the matching part is cut from the task's
title. How a platform marks deadlines depends on the platform and its language, so look at the titles in
your feed first. A Moodle calendar in English might need this:

```bash
CALENDAR_ICS_FEEDS="moodle=https://moodle.example/calendar/export.php?token=..."
CALENDAR_DEADLINES="moodle= is due$"
CALENDAR_FEED_AREAS="moodle=uni"
```

These URLs carry a secret token: anyone with the link can read the calendar. They only live in `.env`,
and sync errors are logged without them.

Check the first sync in the Tasks tab (calendar view, "fetch now") or on the server with
`curl -u <user> -X POST http://127.0.0.1:8080/api/calendar/sync` (straight to Compass's Caddy, which
asks for the login). Run it twice: the second run must report `"created": 0` for the deadlines, otherwise the feed's UIDs are not
stable.

## 7. Health Connect bridge on the phone

Sleep and health data arrive from the Android app in `android/` (build and setup in its README).
It posts to `/api/ingest/healthconnect` on the dashboard address. That path is exempt from the
basic auth in Caddy and needs a bearer token instead:

| Variable | Value |
|---|---|
| `HEALTHCONNECT_TOKEN` | output of `openssl rand -hex 32`; empty disables the endpoint (503) |
| `HEALTHCONNECT_GYMDAY_APPS` | package of Gym Day (default `com.anthonyng.workoutapp`), for the session durations |

After `make deploy`, check the token from your computer:
`curl -H "Authorization: Bearer <token>" https://<dashboard host>/api/ingest/healthconnect`
must answer `{"ok": true, ...}`. Enter the same address and token in the app. The phone reaches the
server over the VPN like the dashboard, nothing new becomes public.

A sync only derives the days it changes. When a release derives something new from the records
(for example meals, or Gym Day sessions without an export), recompute it once for the records that
are already stored:

```bash
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml \
  exec api python -m app.cli rebuild-health
```

It prints the number of days and Gym Day sessions and can be run again at any time.

## 8. Mails

The worker reads the configured mailboxes every `MAIL_SYNC_MINUTES` over IMAP, read-only (`EXAMINE`,
`BODY.PEEK`): nothing is marked as read, moved or deleted. Only sender, subject, time and the triage
(priority, summary, suggested task) are stored, never the text.

**Server `.env`:**

| Variable | Value |
|---|---|
| `MAIL_ACCOUNTS` | names of your accounts, separated by spaces, e.g. `gmail work`. Without it, `uni gmail domain` |
| `<NAME>_IMAP_HOST`, `_PORT`, `_USER`, `_PASSWORD` | the login per account, e.g. `WORK_IMAP_HOST`; an account is active when host and user are set. Gmail needs an app password (Google account → Security → App passwords, requires 2FA) |
| `MAIL_TRIAGE_<NAME>` | who summarises its mails: `claude`, `local` or `rules` (the default, headers only) |
| `MAIL_ACCOUNT_AREAS` | area of tasks made from a mail, as `account=area` pairs |
| `ANTHROPIC_API_KEY` | for `claude`, model `MAIL_CLAUDE_MODEL` (default `claude-haiku-4-5`). Without a key these accounts get rule priorities only |
| `MAIL_TRIAGE_TOKEN` | for `local`: output of `openssl rand -hex 32`, the same value goes into the `.env` of the machine with Ollama |

After `make deploy`, "Fetch now" in the Mail tab runs the first sync (the last `MAIL_LOOKBACK_DAYS` days).
Accounts with `claude` are summarised right away, up to 40 mails per run; `local` accounts show "waiting
for the local model" until the local triage ran.

**Local triage on a machine with Ollama** (the mail text stays on that machine, e.g. your laptop):

The server cannot reach that machine, so the machine asks: it fetches the list of pending mails from
`/api/ingest/mail/pending`, reads their text from the mailbox itself, lets Ollama triage them and sends
only the result back.

```bash
sudo systemctl enable --now ollama          # Ollama service, listens on localhost only
ollama pull qwen2.5:7b                      # about 4.7 GB; any model with JSON output works (OLLAMA_MODEL)
```

In that machine's `.env` (the one in the repo checkout): `MAIL_ACCOUNTS` and the IMAP login of the
account, `COMPASS_URL=https://<dashboard host>`, `MAIL_TRIAGE_TOKEN` (same as on the server), optionally
`OLLAMA_MODEL`. Test once by hand, then install the timer (every 15 minutes while the machine is on,
catches up after sleep):

```bash
cd backend && uv run python -m app.mail.local_triage     # prints e.g. {"pending": 3, "applied": 3, "failed": 0}
mkdir -p ~/.config/systemd/user
sed "s|@REPO@|$(git rev-parse --show-toplevel)|" infra/laptop/compass-mail-triage.service \
  > ~/.config/systemd/user/compass-mail-triage.service
cp infra/laptop/compass-mail-triage.timer ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now compass-mail-triage.timer
journalctl --user -u compass-mail-triage -n 20            # last runs
```

The model reads untrusted text. A mail that tries to give instructions to an AI is detected with a pattern
check (independent of what the model says), marked with a warning and never ranked below "normal".

## Sharing a workout export from the phone

The installed PWA is a share target for CSV files. After an update that changed the share target,
Android may need a day to refresh the installed app. If Compass does not show up when sharing the export,
remove the app from the home screen and install it again from the browser.

## Updating

### Automatically

A timer on the server checks `main` every two minutes. Once CI has pushed the images for the newest
commit, it pulls the commit, writes a database dump, and restarts the changed containers. If CI fails, no
images appear and the server stays on the old version. One-time setup:

```bash
cd /opt/compass
sudo cp infra/deploy/systemd/compass-deploy.{service,timer} /etc/systemd/system/
sudo sed -i "s/^User=compass/User=$USER/" /etc/systemd/system/compass-deploy.service
sudo systemctl daemon-reload
sudo systemctl enable --now compass-deploy.timer
```

Follow it with `journalctl -u compass-deploy -f`. The deployed commit is in `/opt/compass/.deployed`.
To pause automatic updates, run `sudo systemctl stop compass-deploy.timer`.

To roll back, stop the timer and start the images of an older commit (CI tags every image with its
commit). Then push a revert to `main` and start the timer again:

```bash
sudo systemctl stop compass-deploy.timer
COMPASS_VERSION=<sha> docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d
```

A rollback does not undo database migrations; the dump written before each update has the old state.

### By hand

Push to `main` and wait for CI to finish. Then run on the server:

```bash
cd /opt/compass && make deploy
```
