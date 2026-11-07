"""IMAP sync: new mails of every configured account become `emails` rows (metadata only).

Per folder the sync remembers UIDVALIDITY and the highest UID it has seen (in integration_state),
so a run only fetches newer mails. The first run, or a folder whose UIDVALIDITY changed, looks
MAIL_LOOKBACK_DAYS back; rows are unique per account and Message-ID, so nothing doubles.

Every mail gets a priority from its headers right away. Mails of accounts with triage "claude"
are then summarised here, a limited number per run so a full inbox does not cost much at once.
Accounts with triage "local" wait for the laptop (app.mail.local_triage).
"""

import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MailAccount, get_settings
from app.mail import imap, triage
from app.models.integrations import IntegrationState
from app.models.mail import Email
from app.services import integrations
from app.services import mail as mail_service
from app.services.clock import local_today, utc_now

log = logging.getLogger("compass.mail")

# Summaries per account and run; the rest follows in the next runs.
CLAUDE_PER_RUN = 40
# Seen flags are refreshed for mails this recent.
FLAG_DAYS = 14

MailboxFactory = Callable[[MailAccount], imap.Mailbox]


def state_name(account: str) -> str:
    return f"mail:{account}"


def _store(session: Session, account: MailAccount, headers: list[imap.Header]) -> int:
    if not headers:
        return 0
    existing = {
        e.msg_key: e
        for e in session.scalars(
            select(Email).where(
                Email.account == account.name, Email.msg_key.in_({h.msg_key for h in headers})
            )
        )
    }
    created = 0
    for h in headers:
        row = existing.get(h.msg_key)
        if row is not None:
            # Moved or re-numbered in the mailbox: follow it, keep the triage.
            row.folder, row.uidvalidity, row.uid, row.seen = h.folder, h.uidvalidity, h.uid, h.seen
            row.removed_at = None
            continue
        priority, category = triage.rules(h)
        # Mailing lists and newsletters are not worth a model call.
        wants_model = account.triage in ("claude", "local") and not h.bulk
        row = Email(
            account=account.name,
            msg_key=h.msg_key,
            folder=h.folder,
            uidvalidity=h.uidvalidity,
            uid=h.uid,
            from_name=h.from_name,
            from_addr=h.from_addr,
            subject=h.subject,
            received_at=h.received_at,
            seen=h.seen,
            bulk=h.bulk,
            priority=priority,
            category=category,
            triage="pending" if wants_model else "rules",
        )
        session.add(row)
        existing[h.msg_key] = row
        created += 1
    session.flush()
    return created


def _refresh_seen(session: Session, box: imap.Mailbox, account: str, folder: str, validity: int):
    """Seen flags of recent mails, and which of them are gone: a mail deleted, archived or moved
    to a folder that is not synced no longer answers in its folder and leaves the list."""
    since = utc_now() - timedelta(days=FLAG_DAYS)
    recent = list(
        session.scalars(
            select(Email).where(
                Email.account == account,
                Email.folder == folder,
                Email.uidvalidity == validity,
                Email.received_at >= since,
            )
        )
    )
    if not recent:
        return
    flags = box.seen_flags([e.uid for e in recent])
    now = utc_now()
    for e in recent:
        if e.uid in flags:
            e.seen = flags[e.uid]
            e.removed_at = None
        elif e.removed_at is None:
            e.removed_at = now


def _summarise_with_claude(session: Session, box: imap.Mailbox, account: MailAccount) -> dict:
    settings = get_settings()
    pending = list(
        session.scalars(
            select(Email)
            .where(
                Email.account == account.name,
                Email.triage == "pending",
                Email.removed_at.is_(None),
            )
            .order_by(Email.received_at.desc())
            .limit(CLAUDE_PER_RUN)
        )
    )
    done = failed = 0
    open_folder: tuple[str, int] | None = None
    for e in pending:
        try:
            if open_folder is None or open_folder[0] != e.folder:
                open_folder = (e.folder, box.examine(e.folder))
            if open_folder[1] != e.uidvalidity:
                raise triage.TriageError("mailbox renumbered, mail not found", retry=False)
            text = box.text(e.uid)
            result = triage.claude(
                settings.anthropic_api_key,
                settings.mail_claude_model,
                triage.prompt(mail_service.sender(e), e.subject, e.received_at.isoformat(), text),
            )
        except triage.TriageError as exc:
            failed += 1
            e.triage_error = str(exc)[:500]
            if exc.retry:
                # The API is down or rate limited: stop for this run, try again next time.
                break
            e.triage = "rules"  # keeps the rule priority, no summary
            continue
        mail_service.apply_triage(e, result, "claude")
        done += 1
    session.flush()
    return {"summarised": done, "triage_failed": failed}


def sync_account(
    session: Session, account: MailAccount, mailbox: MailboxFactory = imap.Mailbox
) -> dict:
    state = session.get(IntegrationState, state_name(account.name))
    cursor: dict = dict((state.stats or {}).get("cursor", {})) if state else {}
    lookback = local_today() - timedelta(days=get_settings().mail_lookback_days)

    stats: dict = {"new": 0}
    with mailbox(account) as box:
        for folder in account.folders:
            validity = box.examine(folder)
            known = cursor.get(folder)
            if known and known.get("uidvalidity") == validity:
                uids = box.uids_after(known["last_uid"])
                last = known["last_uid"]
            else:
                uids = box.uids_since(lookback)
                last = 0
            stats["new"] += _store(session, account, box.headers(uids, validity))
            cursor[folder] = {"uidvalidity": validity, "last_uid": max([last, *uids])}
            _refresh_seen(session, box, account.name, folder, validity)
        if account.triage == "claude":
            stats.update(_summarise_with_claude(session, box, account))

    stats["pending"] = len(
        session.scalars(
            select(Email.id).where(Email.account == account.name, Email.triage == "pending")
        ).all()
    )
    integrations.record_success(
        session, state_name(account.name), {**stats, "triage": account.triage, "cursor": cursor}
    )
    return stats


def sync_all(session_factory, mailbox: MailboxFactory = imap.Mailbox) -> dict[str, dict | str]:
    """Sync every configured account in its own transaction; one failing account does not stop
    the others. Errors never contain the password."""
    try:
        accounts = get_settings().mail_accounts
    except ValueError as exc:
        return {"config": str(exc)}
    results: dict[str, dict | str] = {}
    for name, account in accounts.items():
        with session_factory() as session:
            try:
                results[name] = sync_account(session, account, mailbox)
                session.commit()
            except Exception as exc:  # IMAP, network, TLS, login
                session.rollback()
                error = f"{exc.__class__.__name__}: {exc}"[:500]
                log.warning("mail sync %s failed: %s", name, error)
                integrations.record_failure(session, state_name(name), error)
                session.commit()
                results[name] = error
    return results
