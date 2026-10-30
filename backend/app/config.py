import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import dotenv_values
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class MailAccount:
    name: str
    host: str
    port: int
    user: str
    password: str = field(repr=False)
    folders: tuple[str, ...]
    triage: str


ENV_FILES = ("../.env", ".env")
# Hosts that are the same for everybody, so the variable can stay unset.
KNOWN_IMAP_HOSTS = {"gmail": "imap.gmail.com"}


def _pairs(value: str) -> dict[str, str]:
    """Space separated key=value pairs, lowercase."""
    out = {}
    for pair in value.split():
        key, sep, item = pair.partition("=")
        if sep and key and item:
            out[key.strip().lower()] = item.strip().lower()
    return out


def _variable(name: str, default: str = "") -> str:
    """A variable whose name is not known in advance: the environment beats the .env files, like
    for the fields of Settings."""
    if name in os.environ:
        return os.environ[name]
    found = None
    for path in ENV_FILES:
        found = dotenv_values(path).get(name, found)
    return default if found is None else found


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    postgres_user: str = "compass"
    postgres_password: str = "compass"
    postgres_db: str = "compass"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    timezone: str = "Europe/Berlin"
    log_level: str = "INFO"
    # Language of the texts the server writes itself (push notifications, the weekly review, mail
    # summaries, the MCP prompts): "en" or "de". The web app follows the browser instead.
    compass_language: str = "en"

    # MCP server and its built-in OAuth server. The public URL is what Claude connects to;
    # the MCP endpoint is <public url>/mcp.
    mcp_public_url: str = "http://localhost:8001"
    mcp_access_token_ttl: int = 3600
    mcp_refresh_token_ttl: int = 60 * 60 * 24 * 30
    mcp_write_limit_per_hour: int = 120

    # The owner login, shared with the Caddy basic auth in front of the web app.
    compass_basic_auth_user: str = ""
    compass_basic_auth_hash: str = ""

    # Calendar feeds (ICS). Entries of a deadline feed become tasks instead of events: the ILIAS
    # feed by its suffixes below, any other feed by a pattern in calendar_deadlines.
    # Other feeds: space separated name=url pairs, e.g. "google=https://... uni=https://...".
    ilias_ics_url: str = ""
    calendar_ics_feeds: str = ""
    calendar_sync_minutes: int = 30
    # Semicolon separated feed=regex: entries of that feed whose title matches become tasks, and the
    # matching part is cut from the title, e.g. "moodle= is due$". Case does not matter.
    calendar_deadlines: str = ""
    # Area per calendar (space separated feed=area slug): its events get that area's colour and
    # follow the area filter. Calendars without an entry have no area.
    calendar_feed_areas: str = ""
    # ILIAS marks exercise deadlines with this suffix in the title (German and English UI).
    ilias_deadline_suffixes: str = "(Abgabetermin),(Deadline)"
    # Area for new ILIAS deadline tasks (slug); empty means the area of the feed, unknown no area.
    ilias_deadline_area: str = ""

    # Health Connect bridge app on the phone. It sends this token as a bearer token to
    # /api/ingest/healthconnect, which is not behind the basic auth. Empty disables the endpoint.
    healthconnect_token: str = ""
    # Apps whose Health Connect exercise sessions are Gym Day sessions (they give the duration of
    # the sessions from the CSV export). Space separated package names.
    healthconnect_gymday_apps: str = "com.anthonyng.workoutapp"

    # Mail accounts (IMAP, read-only): their names, space or comma separated. Each name has its own
    # variables, see mail_accounts. An account is active when host and user are set.
    mail_account_names: str = Field("uni gmail domain", validation_alias="MAIL_ACCOUNTS")
    # Area of tasks made from a mail, per account (space separated account=area slug).
    mail_account_areas: str = ""
    # Space separated folders per account; Exchange also lists calendars etc. as folders.
    mail_folders: str = "INBOX"
    mail_sync_minutes: int = 15
    # The first sync of an account looks this far back.
    mail_lookback_days: int = 14
    anthropic_api_key: str = ""
    mail_claude_model: str = "claude-haiku-4-5"
    # Laptop side of the local triage.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    compass_url: str = ""
    # Bearer token of the local triage runner for /api/ingest/mail/*. Empty disables it.
    mail_triage_token: str = ""

    # News feeds (RSS/Atom): space separated stream:name=url, stream is "general" or "personal".
    # General items are shown as they come; personal ones are ranked by the interest profile.
    news_feeds: str = (
        "general:bbc=https://feeds.bbci.co.uk/news/world/rss.xml "
        "personal:hn=https://hnrss.org/frontpage?points=100 "
        "personal:lobsters=https://lobste.rs/rss"
    )
    # Bank accounts through Enable Banking (PSD2). The app id and its private key (the PEM file,
    # base64 encoded on one line) come from the Enable Banking control panel; the redirect URL is
    # Compass' /finance page and must be registered for the app there. Empty disables it.
    enablebanking_app_id: str = ""
    enablebanking_private_key: str = ""
    enablebanking_redirect_url: str = ""
    # Banks allow about 4 fetches a day without the user present.
    finance_sync_hours: int = 6
    # The country Enable Banking lists banks of (ISO code).
    finance_country: str = "DE"
    # Built-in merchant rules by country, space separated (see app.services.finance).
    finance_rule_sets: str = "de"

    # Web push (VAPID). Create the pair with: make vapid-keys. Empty disables push.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    # Contact for the push services (mailto: or https: URL); empty uses MCP_PUBLIC_URL.
    vapid_subject: str = ""
    # No notifications from quiet_start to quiet_end o'clock (local), except the bedtime one.
    push_quiet_start: int = 23
    push_quiet_end: int = 8
    # The bedtime reminder comes this long before the latest bedtime.
    push_bedtime_lead_minutes: int = 30

    # The latest bedtime: up this long before the first appointment, before that this much sleep
    # and this long to fall asleep.
    wake_buffer_minutes: int = 120
    sleep_need_minutes: int = 450
    fall_asleep_minutes: int = 30
    # Zone 2 as a share of the maximum heart rate.
    zone2_min_percent: int = 60
    zone2_max_percent: int = 70

    news_sync_minutes: int = 60
    # Items older than this are removed; the learned profile keeps what their thumbs taught.
    news_keep_days: int = 30

    @property
    def news_feed_list(self) -> list[tuple[str, str, str]]:
        """(stream, name, url) per configured feed."""
        out = []
        for number, entry in enumerate(self.news_feeds.split(), start=1):
            stream, _, rest = entry.partition(":")
            name, sep, url = rest.partition("=")
            if (
                stream not in ("general", "personal")
                or not sep
                or not url.startswith(("https://", "http://"))
                or not re.fullmatch(r"[a-z0-9_-]{1,40}", name)
            ):
                raise ValueError(
                    f"NEWS_FEEDS: entry {number} is not stream:name=url "
                    "(e.g. personal:hn=https://hnrss.org/frontpage)"
                )
            out.append((stream, name, url))
        return out

    @property
    def mail_accounts(self) -> dict[str, "MailAccount"]:
        """Configured accounts by name. Each name in MAIL_ACCOUNTS has <NAME>_IMAP_HOST, _PORT,
        _USER and _PASSWORD, and MAIL_TRIAGE_<NAME>. Without that, an account gets priorities from
        its headers only: its mails may hold personal data of others, so sending them to a model is
        a choice to make per account."""
        out = {}
        for name in re.split(r"[,\s]+", self.mail_account_names.strip().lower()):
            if not name:
                continue
            if not re.fullmatch(r"[a-z0-9_]{1,20}", name):
                raise ValueError(f"MAIL_ACCOUNTS: {name!r} is not a name (a-z, 0-9, _)")
            prefix = name.upper()
            host = _variable(f"{prefix}_IMAP_HOST", KNOWN_IMAP_HOSTS.get(name, "")).strip()
            user = _variable(f"{prefix}_IMAP_USER").strip()
            if not host or not user:
                continue
            triage = _variable(f"MAIL_TRIAGE_{prefix}", "rules").strip().lower()
            if triage not in ("claude", "local", "rules"):
                raise ValueError(f"MAIL_TRIAGE_{prefix}: use claude, local or rules")
            if triage == "claude" and not self.anthropic_api_key:
                triage = "rules"
            out[name] = MailAccount(
                name=name,
                host=host,
                port=int(_variable(f"{prefix}_IMAP_PORT", "993")),
                user=user,
                password=_variable(f"{prefix}_IMAP_PASSWORD"),
                folders=tuple(self.mail_folders.split()) or ("INBOX",),
                triage=triage,
            )
        return out

    @property
    def mail_area_map(self) -> dict[str, str]:
        return _pairs(self.mail_account_areas)

    @property
    def owner_password_hash(self) -> str:
        # In .env every $ of the bcrypt hash is written as $$ for Docker Compose.
        return self.compass_basic_auth_hash.replace("$$", "$")

    @property
    def mcp_resource_url(self) -> str:
        return self.mcp_public_url.rstrip("/") + "/mcp"

    @property
    def gymday_apps(self) -> set[str]:
        return set(self.healthconnect_gymday_apps.split())

    @property
    def calendar_area_map(self) -> dict[str, str]:
        return _pairs(self.calendar_feed_areas)

    @property
    def deadline_patterns(self) -> dict[str, re.Pattern]:
        """Per feed, what marks an entry as a deadline."""
        out = {}
        suffixes = [s.strip() for s in self.ilias_deadline_suffixes.split(",") if s.strip()]
        if suffixes:
            out["ilias"] = re.compile("(?:" + "|".join(map(re.escape, suffixes)) + r")\s*$")
        for number, entry in enumerate(self.calendar_deadlines.split(";"), start=1):
            if not entry.strip():
                continue
            feed, sep, pattern = entry.partition("=")
            try:
                if not sep or not feed.strip() or not pattern:
                    raise re.error("no pattern")
                out[feed.strip().lower()] = re.compile(pattern, re.IGNORECASE)
            except re.error:
                raise ValueError(
                    f"CALENDAR_DEADLINES: entry {number} is not feed=regex (e.g. moodle= is due$)"
                ) from None
        return out

    @property
    def calendar_feeds(self) -> dict[str, str]:
        """All configured feeds by name. "ilias" is reserved for ILIAS_ICS_URL."""
        feeds: dict[str, str] = {}
        if self.ilias_ics_url.strip():
            feeds["ilias"] = self.ilias_ics_url.strip()
        for number, pair in enumerate(self.calendar_ics_feeds.split(), start=1):
            name, sep, url = pair.partition("=")
            # Never echo the entry: the URL carries a secret token and errors end up in logs.
            if not sep or not url or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise ValueError(
                    f"CALENDAR_ICS_FEEDS: entry {number} is not name=url (e.g. google=https://...)"
                )
            if name == "ilias":
                raise ValueError('CALENDAR_ICS_FEEDS: "ilias" is reserved, use ILIAS_ICS_URL')
            feeds[name.lower()] = url
        return feeds

    @property
    def language(self) -> str:
        return "de" if self.compass_language.strip().lower().startswith("de") else "en"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
