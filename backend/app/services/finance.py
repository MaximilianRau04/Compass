"""Money: bank accounts through Enable Banking, categories, budgets, recurring payments and the
securities account (entered by hand).

- Connecting: the user picks the bank, approves at the bank and comes back with a code; the
  consent lasts up to 180 days, then the user approves again.
- Sync: booked transactions only (pending ones change their ids when booked). Each sync fetches
  again from 10 days before the newest booking, so late bookings are not missed; the external id
  keeps it free of duplicates.
- Categories: the user's rules first, then the built-in ones; a match on counterparty or purpose
  sets the category. Money in without a match is income. Claude sorts the rest (MCP).
- Months: spending is the money out in spending categories (refunds in the same category count
  against it); "savings" (to the securities account) and "transfer" (own accounts) are not
  spending.
"""

import hashlib
import logging
import re
import secrets
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.finance import (
    BankAccount,
    BankConnection,
    BankTransaction,
    DepotValue,
    FinanceBudget,
    FinanceRule,
)
from app.services import enablebanking
from app.services.clock import local_today, utc_now

log = logging.getLogger("compass.finance")

SPENDING = (
    "housing",
    "groceries",
    "eating_out",
    "transport",
    "subscriptions",
    "insurance",
    "health",
    "sport",
    "shopping",
    "leisure",
    "education",
    "cash",
    "fees",
    "other",
)
CATEGORIES = (*SPENDING, "income", "savings", "transfer")

# Lowercase substrings of counterparty or purpose. The user's rules (FinanceRule) come first, then
# the sets of FINANCE_RULE_SETS, then the international ones.
RULES_BY_COUNTRY: dict[str, tuple[tuple[str, str], ...]] = {
    "de": (
        ("trade republic", "savings"),
        ("miete", "housing"),
        ("stadtwerke", "housing"),
        ("rundfunk", "housing"),
        ("rewe", "groceries"),
        ("edeka", "groceries"),
        ("aldi", "groceries"),
        ("lidl", "groceries"),
        ("netto", "groceries"),
        ("penny", "groceries"),
        ("kaufland", "groceries"),
        ("dm-drogerie", "groceries"),
        ("dm drogerie", "groceries"),
        ("rossmann", "groceries"),
        ("lieferando", "eating_out"),
        ("mensa", "eating_out"),
        ("studierendenwerk", "eating_out"),
        ("deutsche bahn", "transport"),
        ("db vertrieb", "transport"),
        ("flixbus", "transport"),
        ("aral", "transport"),
        ("tankstelle", "transport"),
        ("versicherung", "insurance"),
        ("huk-coburg", "insurance"),
        ("apotheke", "health"),
        ("mcfit", "sport"),
        ("fitx", "sport"),
        ("urban sports", "sport"),
        ("zalando", "shopping"),
        ("geldautomat", "cash"),
        ("bargeldauszahlung", "cash"),
        ("kontoführung", "fees"),
        ("entgelt", "fees"),
        ("lohn", "income"),
        ("gehalt", "income"),
        ("bezüge", "income"),
        ("bafög", "income"),
    ),
}
INTERNATIONAL_RULES: tuple[tuple[str, str], ...] = (
    ("wolt", "eating_out"),
    ("uber eats", "eating_out"),
    ("mcdonald", "eating_out"),
    ("burger king", "eating_out"),
    ("shell", "transport"),
    ("esso", "transport"),
    ("spotify", "subscriptions"),
    ("netflix", "subscriptions"),
    ("disney plus", "subscriptions"),
    ("youtube", "subscriptions"),
    ("apple.com", "subscriptions"),
    ("google play", "subscriptions"),
    ("anthropic", "subscriptions"),
    ("openai", "subscriptions"),
    ("github", "subscriptions"),
    ("hetzner", "subscriptions"),
    ("allianz", "insurance"),
    ("amazon", "shopping"),
    ("decathlon", "shopping"),
)

# Each sync starts this far before the newest booking it already has.
OVERLAP_DAYS = 10
FIRST_SYNC_DAYS = 365
MAX_CONSENT = timedelta(days=180)
CONSENT_WARNING = timedelta(days=7)


class FinanceError(ValueError):
    pass


# --- Connecting --------------------------------------------------------------------------------


def start_connect(session: Session, name: str, country: str, client=None) -> str:
    """Create a pending connection and return the bank's login URL."""
    client = client or enablebanking
    redirect = get_settings().enablebanking_redirect_url.strip()
    if not client.configured() or not redirect:
        raise FinanceError(
            "Enable Banking is not set up (ENABLEBANKING_APP_ID, ENABLEBANKING_PRIVATE_KEY, "
            "ENABLEBANKING_REDIRECT_URL)"
        )
    bank = next((a for a in client.aspsps(country) if a["name"] == name), None)
    if bank is None:
        raise FinanceError(f"unknown bank {name!r} in {country}")
    longest = timedelta(seconds=bank.get("maximum_consent_validity") or MAX_CONSENT.total_seconds())
    valid_until = utc_now() + min(longest, MAX_CONSENT) - timedelta(minutes=5)
    state = secrets.token_urlsafe(24)
    session.add(BankConnection(aspsp_name=name, aspsp_country=country, state=state))
    session.flush()
    return client.start_auth(name, country, valid_until.isoformat(), state, redirect)


def finish_connect(session: Session, code: str, state: str, client=None) -> BankConnection:
    """The bank sent the user back: open the session and take over its accounts."""
    client = client or enablebanking
    conn = session.scalar(
        select(BankConnection).where(
            BankConnection.state == state, BankConnection.status == "pending"
        )
    )
    if conn is None:
        raise FinanceError("this approval is unknown or was already used")
    data = client.create_session(code)
    conn.session_id = data["session_id"]
    conn.valid_until = datetime.fromisoformat(data["access"]["valid_until"])
    conn.status, conn.state, conn.last_error = "active", None, None
    for a in data.get("accounts") or []:
        ident = a.get("identification_hash") or a["uid"]
        account = session.scalar(
            select(BankAccount).where(BankAccount.identification_hash == ident)
        )
        if account is None:
            account = BankAccount(identification_hash=ident, name="")
            session.add(account)
        elif account.connection_id and account.connection_id != conn.id:
            # The account moves to the new consent; the old one has done its job.
            old = session.get(BankConnection, account.connection_id)
            if old is not None and old.status == "active":
                old.status = "replaced"
        iban = (a.get("account_id") or {}).get("iban")
        account.uid = a["uid"]
        account.connection = conn
        account.iban = iban
        account.currency = a.get("currency") or "EUR"
        account.name = a.get("name") or a.get("product") or iban or "Konto"
    session.flush()
    return conn


def disconnect(session: Session, connection_id: int, client=None) -> None:
    client = client or enablebanking
    conn = session.get(BankConnection, connection_id)
    if conn is None:
        raise FinanceError("unknown connection")
    if conn.session_id and conn.status == "active":
        try:
            client.request("DELETE", f"/sessions/{conn.session_id}")
        except enablebanking.BankingError as exc:
            log.warning("finance: closing session failed: %s", exc)
    conn.status = "revoked"
    session.flush()


# --- Sync --------------------------------------------------------------------------------------


def _amount(t: dict) -> Decimal:
    value = abs(Decimal(str(t["transaction_amount"]["amount"])))
    return -value if t.get("credit_debit_indicator") == "DBIT" else value


def _parse(t: dict) -> dict:
    out = _amount(t) < 0
    party = (t.get("creditor") if out else t.get("debtor")) or {}
    party_account = (t.get("creditor_account") if out else t.get("debtor_account")) or {}
    purpose = " ".join(x for x in (t.get("remittance_information") or []) if x) or t.get("note")
    booked = t.get("booking_date") or t.get("value_date") or t.get("transaction_date")
    return {
        "booking_date": date.fromisoformat(booked),
        "amount": _amount(t),
        "currency": t["transaction_amount"].get("currency") or "EUR",
        "counterparty": (party.get("name") or "").strip()[:200] or None,
        "counterparty_iban": party_account.get("iban"),
        "purpose": " ".join((purpose or "").split()) or None,
    }


def _external_ids(raw: list[dict], parsed: list[dict]) -> list[str]:
    """The bank's id, or a hash of the content plus a counter for identical ones on a day."""
    seen: dict[str, int] = defaultdict(int)
    out = []
    for t, p in zip(raw, parsed, strict=True):
        ident = t.get("entry_reference") or t.get("transaction_id")
        if not ident:
            base = "|".join(
                str(p[k]) for k in ("booking_date", "amount", "counterparty", "purpose")
            )
            digest = hashlib.sha1(base.encode()).hexdigest()[:24]
            seen[digest] += 1
            ident = f"h:{digest}:{seen[digest]}"
        out.append(str(ident)[:200])
    return out


BALANCE_TYPES = ("CLBD", "ITBD", "XPCD", "CLAV", "ITAV", "OTHR")


def _balance(balances: list[dict]) -> Decimal | None:
    by_type = {b.get("balance_type"): b for b in balances}
    for kind in BALANCE_TYPES:
        if kind in by_type:
            return Decimal(str(by_type[kind]["balance_amount"]["amount"]))
    return Decimal(str(balances[0]["balance_amount"]["amount"])) if balances else None


def sync_account(session: Session, account: BankAccount, today: date, client=None) -> int:
    client = client or enablebanking
    assert account.uid
    newest = session.scalar(
        select(func.max(BankTransaction.booking_date)).where(
            BankTransaction.account_id == account.id
        )
    )
    since = newest - timedelta(days=OVERLAP_DAYS) if newest else today - timedelta(FIRST_SYNC_DAYS)
    raw = client.transactions(account.uid, since.isoformat())
    parsed = [_parse(t) for t in raw]
    known = set(
        session.scalars(
            select(BankTransaction.external_id).where(BankTransaction.account_id == account.id)
        )
    )
    rules = rule_list(session)
    created = 0
    for ident, p in zip(_external_ids(raw, parsed), parsed, strict=True):
        if ident in known:
            continue
        known.add(ident)
        t = BankTransaction(account_id=account.id, external_id=ident, **p)
        t.category = categorize(t, rules)
        t.category_source = "rule" if t.category else None
        session.add(t)
        created += 1
    balance = _balance(client.balances(account.uid))
    if balance is not None:
        account.balance, account.balance_at = balance, utc_now()
    session.flush()
    return created


def sync(
    session: Session, today: date | None = None, client=None, force: bool = False
) -> dict[str, int]:
    """Fetch new transactions of all accounts with an active consent. Without force, a
    connection synced less than FINANCE_SYNC_HOURS ago is left alone (banks allow about 4
    fetches a day, and every worker restart would use one)."""
    client = client or enablebanking
    today = today or local_today()
    pause = timedelta(hours=get_settings().finance_sync_hours) - timedelta(minutes=10)
    out: dict[str, int] = {}
    for conn in session.scalars(select(BankConnection).where(BankConnection.status == "active")):
        if conn.valid_until and conn.valid_until <= utc_now():
            conn.status = "expired"
            continue
        if not force and conn.last_sync_at and utc_now() - conn.last_sync_at < pause:
            continue
        accounts = session.scalars(
            select(BankAccount).where(BankAccount.connection_id == conn.id)
        ).all()
        try:
            for account in accounts:
                out[account.name] = sync_account(session, account, today, client)
        except enablebanking.BankingError as exc:
            conn.last_error = str(exc)[:2000]
            if exc.status in (401, 403):
                conn.status = "expired"
            log.warning("finance: %s: %s", conn.aspsp_name, exc)
        else:
            conn.last_error = None
            conn.last_sync_at = utc_now()
    session.flush()
    return out


# --- Categories --------------------------------------------------------------------------------


def check_category(category: str) -> str:
    if category not in CATEGORIES:
        raise FinanceError(f"unknown category {category!r}, known: {', '.join(CATEGORIES)}")
    return category


def rule_list(session: Session) -> list[tuple[str, str]]:
    own = [(r.pattern, r.category) for r in session.scalars(select(FinanceRule))]
    # Longer patterns first: "amazon prime" beats "amazon".
    sets = get_settings().finance_rule_sets.lower().split()
    built_in = [rule for name in sets for rule in RULES_BY_COUNTRY.get(name, ())]
    return sorted(own, key=lambda r: -len(r[0])) + built_in + list(INTERNATIONAL_RULES)


def categorize(t: BankTransaction, rules: list[tuple[str, str]]) -> str | None:
    text = f"{t.counterparty or ''} {t.purpose or ''}".lower()
    for pattern, category in rules:
        if pattern in text:
            return category
    return "income" if t.amount > 0 else None


def set_category(
    session: Session, transaction_id: int, category: str, source: str = "manual"
) -> BankTransaction:
    t = session.get(BankTransaction, transaction_id)
    if t is None:
        raise FinanceError(f"unknown transaction {transaction_id}")
    t.category, t.category_source = check_category(category), source
    session.flush()
    return t


def add_rule(session: Session, pattern: str, category: str) -> int:
    """Store a rule and apply it to every transaction not sorted by hand. Returns how many
    changed."""
    pattern = " ".join(pattern.lower().split())
    if len(pattern) < 3:
        raise FinanceError("the pattern needs at least 3 characters")
    check_category(category)
    rule = session.scalar(select(FinanceRule).where(FinanceRule.pattern == pattern))
    if rule is None:
        session.add(FinanceRule(pattern=pattern, category=category))
    else:
        rule.category = category
    session.flush()
    rules = rule_list(session)
    changed = 0
    for t in session.scalars(
        select(BankTransaction).where(
            (BankTransaction.category_source.is_(None))
            | (BankTransaction.category_source == "rule")
        )
    ):
        new = categorize(t, rules)
        if new != t.category:
            t.category, t.category_source = new, "rule" if new else None
            changed += 1
    session.flush()
    return changed


def set_budget(session: Session, category: str, amount: float) -> None:
    if category not in SPENDING:
        raise FinanceError(f"budgets are for spending categories: {', '.join(SPENDING)}")
    budget = session.get(FinanceBudget, category)
    if amount <= 0:
        if budget is not None:
            session.delete(budget)
    elif budget is None:
        session.add(FinanceBudget(category=category, amount=Decimal(str(amount))))
    else:
        budget.amount = Decimal(str(amount))
    session.flush()


def transactions(
    session: Session,
    days: int = 30,
    category: str | None = None,
    uncategorized: bool = False,
    query: str | None = None,
    limit: int = 200,
) -> list[BankTransaction]:
    stmt = select(BankTransaction).where(
        BankTransaction.booking_date >= local_today() - timedelta(days=days - 1)
    )
    if category:
        stmt = stmt.where(BankTransaction.category == category)
    if uncategorized:
        stmt = stmt.where(BankTransaction.category.is_(None))
    if query:
        like = f"%{query.lower()}%"
        stmt = stmt.where(
            func.lower(func.coalesce(BankTransaction.counterparty, "")).like(like)
            | func.lower(func.coalesce(BankTransaction.purpose, "")).like(like)
        )
    stmt = stmt.order_by(BankTransaction.booking_date.desc(), BankTransaction.id.desc())
    return list(session.scalars(stmt.limit(limit)))


# --- Depot -------------------------------------------------------------------------------------


def log_depot(session: Session, value: float, day: date | None = None) -> date:
    day = day or local_today()
    if day > local_today():
        raise FinanceError("the day is in the future")
    if value < 0:
        raise FinanceError("the value cannot be negative")
    row = session.get(DepotValue, day)
    if row is None:
        session.add(DepotValue(local_date=day, value=Decimal(str(value))))
    else:
        row.value = Decimal(str(value))
    session.flush()
    return day


# --- Overview ----------------------------------------------------------------------------------


@dataclass
class Month:
    month: str  # YYYY-MM
    income: float
    spending: float
    saved: float  # to the securities account
    by_category: dict[str, float]  # spending per category, positive
    uncategorized: int


@dataclass
class Recurring:
    name: str
    category: str | None
    amount: float  # per payment, positive
    interval: str  # monthly | quarterly | yearly
    monthly_cost: float
    last_date: date
    next_date: date
    count: int


@dataclass
class Overview:
    months: list[Month]
    budgets: dict[str, float]
    balances: list[BankAccount]
    connections: list[BankConnection]
    depot: list[DepotValue]
    invested: float  # all money to the securities account in the data
    recurring: list[Recurring] = field(default_factory=list)

    @property
    def cash(self) -> float:
        return float(sum(a.balance or 0 for a in self.balances))

    @property
    def depot_value(self) -> float | None:
        return float(self.depot[-1].value) if self.depot else None


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _months_back(today: date, n: int) -> list[str]:
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return list(reversed(out))


def months(session: Session, n: int = 6, today: date | None = None) -> list[Month]:
    today = today or local_today()
    keys = _months_back(today, n)
    first = date.fromisoformat(keys[0] + "-01")
    data = {k: Month(k, 0.0, 0.0, 0.0, defaultdict(float), 0) for k in keys}
    for t in session.scalars(select(BankTransaction).where(BankTransaction.booking_date >= first)):
        m = data.get(_month_key(t.booking_date))
        if m is None:
            continue
        amount = float(t.amount)
        if t.category == "transfer":
            continue
        if t.category == "savings":
            m.saved -= amount
        elif t.category == "income":
            m.income += amount
        elif t.category in SPENDING or (t.category is None and amount < 0):
            m.spending -= amount
            m.by_category[t.category or "uncategorized"] -= amount
            if t.category is None:
                m.uncategorized += 1
    out = []
    for m in data.values():
        m.by_category = {
            k: round(v, 2) for k, v in sorted(m.by_category.items(), key=lambda x: -x[1])
        }
        m.income, m.spending, m.saved = round(m.income, 2), round(m.spending, 2), round(m.saved, 2)
        out.append(m)
    return out


def _norm(text: str | None) -> str:
    return " ".join(re.sub(r"[^a-zäöüß]+", " ", (text or "").lower()).split())[:40]


INTERVALS = (("monthly", 25, 35, 1), ("quarterly", 85, 97, 3), ("yearly", 355, 375, 12))


def recurring(session: Session, today: date | None = None) -> list[Recurring]:
    """Payments with the same payee and amount at a regular interval, still running."""
    today = today or local_today()
    groups: dict[tuple[str, Decimal], list[BankTransaction]] = defaultdict(list)
    for t in session.scalars(
        select(BankTransaction).where(
            BankTransaction.amount < 0,
            BankTransaction.booking_date >= today - timedelta(days=400),
        )
    ):
        if t.category in ("transfer", "savings"):
            continue
        party = _norm(t.counterparty)
        # PayPal pays everybody: the merchant is in the purpose.
        name = f"paypal {_norm(t.purpose)}" if "paypal" in party or not party else party
        groups[(name, t.amount)].append(t)
    out = []
    for (_, amount), items in groups.items():
        items.sort(key=lambda t: t.booking_date)
        dates = sorted({t.booking_date for t in items})
        if len(dates) < 2:
            continue
        gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
        gap = median(gaps)
        for interval, low, high, months_per in INTERVALS:
            need = 2 if interval == "yearly" else 3
            if low <= gap <= high and len(dates) >= need:
                last = dates[-1]
                if (today - last).days > gap * 1.5:
                    break  # ended
                t = items[-1]
                label = t.counterparty or t.purpose or "?"
                if t.counterparty and "paypal" in t.counterparty.lower() and t.purpose:
                    # Without the reference numbers: "1057 PP.1180 Netflix" -> "Netflix"
                    label = " ".join(re.sub(r"\S*\d\S*", " ", t.purpose).split()) or t.purpose
                out.append(
                    Recurring(
                        name=label[:80],
                        category=t.category,
                        amount=float(-amount),
                        interval=interval,
                        monthly_cost=round(float(-amount) / months_per, 2),
                        last_date=last,
                        next_date=last + timedelta(days=round(gap)),
                        count=len(dates),
                    )
                )
                break
    return sorted(out, key=lambda r: -r.monthly_cost)


def overview(session: Session, n: int = 6, today: date | None = None) -> Overview:
    today = today or local_today()
    invested = session.scalar(
        select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
            BankTransaction.category == "savings"
        )
    )
    return Overview(
        months=months(session, n, today),
        budgets={b.category: float(b.amount) for b in session.scalars(select(FinanceBudget))},
        balances=list(session.scalars(select(BankAccount).order_by(BankAccount.name))),
        connections=list(
            session.scalars(
                select(BankConnection)
                .where(BankConnection.status.in_(("active", "expired")))
                .order_by(BankConnection.created_at.desc())
            )
        ),
        depot=list(session.scalars(select(DepotValue).order_by(DepotValue.local_date))),
        invested=round(-float(invested or 0), 2),
        recurring=recurring(session, today),
    )


def currency(session: Session) -> str:
    """The currency amounts are shown in. Totals assume all accounts share one."""
    return session.scalar(select(BankAccount.currency).order_by(BankAccount.id)) or "EUR"


def expiring(session: Session, now: datetime | None = None) -> list[BankConnection]:
    """Active consents that end within CONSENT_WARNING."""
    now = now or datetime.now(UTC)
    return list(
        session.scalars(
            select(BankConnection).where(
                BankConnection.status == "active",
                BankConnection.valid_until <= now + CONSENT_WARNING,
            )
        )
    )
