"""Local mail triage, run on the laptop (not on the server):

    cd backend && uv run python -m app.mail.local_triage

Asks Compass which mails of accounts with MAIL_TRIAGE_<ACCOUNT>=local still need a summary, reads
their text directly from the mailbox over IMAP (read-only), lets the local Ollama model triage
them and sends back only the result (priority, summary, task title). The text never reaches the
server or any external service.

Needs in the laptop's .env: COMPASS_URL, MAIL_TRIAGE_TOKEN, the IMAP login of the account
(e.g. UNI_IMAP_*), OLLAMA_URL and OLLAMA_MODEL. Meant for a systemd user timer (infra/laptop/);
exits with status 1 if something failed, so the timer shows it.
"""

import imaplib
import json
import logging
import sys
import urllib.request
from collections import defaultdict

from app.config import get_settings
from app.mail import imap, triage

log = logging.getLogger("compass.local_triage")

BATCH = 25


def _api(method: str, path: str, body: dict | None = None):
    settings = get_settings()
    request = urllib.request.Request(
        settings.compass_url.rstrip("/") + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {settings.mail_triage_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def ollama_ready() -> bool:
    settings = get_settings()
    try:
        with urllib.request.urlopen(settings.ollama_url.rstrip("/") + "/api/tags", timeout=5) as r:
            models = {m["name"] for m in json.loads(r.read()).get("models", [])}
    except OSError:
        log.warning("Ollama is not running at %s", settings.ollama_url)
        return False
    if settings.ollama_model not in models and f"{settings.ollama_model}:latest" not in models:
        log.warning(
            "Ollama has no model %s (ollama pull %s)", settings.ollama_model, settings.ollama_model
        )
        return False
    return True


def run_once() -> dict:
    settings = get_settings()
    if not settings.compass_url or not settings.mail_triage_token:
        raise SystemExit("COMPASS_URL and MAIL_TRIAGE_TOKEN must be set")
    if not ollama_ready():
        return {"skipped": "ollama"}

    pending = _api("GET", f"/api/ingest/mail/pending?limit={BATCH}")
    if not pending:
        return {"pending": 0}
    accounts = settings.mail_accounts
    by_account: dict[str, list[dict]] = defaultdict(list)
    for item in pending:
        by_account[item["account"]].append(item)

    results, failed = [], []
    for name, items in by_account.items():
        account = accounts.get(name)
        if account is None:
            log.warning("no IMAP login for %s in this .env, skipping %d mails", name, len(items))
            continue
        with imap.Mailbox(account) as box:
            opened: tuple[str, int] | None = None
            for item in items:
                try:
                    if opened is None or opened[0] != item["folder"]:
                        opened = (item["folder"], box.examine(item["folder"]))
                    if opened[1] != item["uidvalidity"]:
                        raise triage.TriageError("mailbox renumbered", retry=False)
                    text = box.text(item["uid"])
                    result = triage.ollama(
                        settings.ollama_url,
                        settings.ollama_model,
                        triage.prompt(item["sender"], item["subject"], item["received_at"], text),
                    )
                except triage.TriageError as exc:
                    if exc.retry:
                        log.warning("stopping: %s", exc)
                        break
                    failed.append({"id": item["id"], "error": str(exc)[:500]})
                    continue
                results.append({"id": item["id"], **result.model_dump()})

    answer = _api("POST", "/api/ingest/mail/triage", {"results": results, "failed": failed})
    return {"pending": len(pending), **answer}


def main() -> None:
    logging.basicConfig(level=get_settings().log_level, format="%(levelname)s %(message)s")
    try:
        result = run_once()
    except (OSError, imaplib.IMAP4.error) as exc:  # VPN down, offline, login refused
        log.error("%s: %s", exc.__class__.__name__, exc)
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
