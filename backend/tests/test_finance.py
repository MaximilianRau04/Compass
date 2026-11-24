import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import select

from app.config import get_settings
from app.models.finance import BankAccount, BankConnection, BankTransaction
from app.services import enablebanking, finance, notify, push
from app.services.clock import local_today
from tests.test_healthconnect import at
from tests.test_push import device

TODAY = local_today()


def tx(ref, days_ago, amount, party=None, purpose=None, debit=True):
    """A transaction as Enable Banking returns it."""
    side = "creditor" if debit else "debtor"
    out = {
        "entry_reference": ref,
        "transaction_amount": {"amount": f"{amount:.2f}", "currency": "EUR"},
        "credit_debit_indicator": "DBIT" if debit else "CRDT",
        "status": "BOOK",
        "booking_date": (TODAY - timedelta(days=days_ago)).isoformat(),
        "remittance_information": [purpose] if purpose else [],
    }
    if party:
        out[side] = {"name": party}
        out[f"{side}_account"] = {"iban": "DE00123"}
    return out


class FakeBank:
    """Stands in for app.services.enablebanking."""

    BankingError = enablebanking.BankingError

    def __init__(self, transactions=()):
        self.data = list(transactions)
        self.fetches = []

    def configured(self):
        return True

    def aspsps(self, country):
        return [
            {
                "name": "Volksbanken Raiffeisenbanken",
                "country": country,
                "maximum_consent_validity": 90 * 86400,
            }
        ]

    def start_auth(self, name, country, valid_until, state, redirect_url):
        self.state, self.valid_until = state, valid_until
        return f"https://bank.example/auth?state={state}"

    def create_session(self, code):
        assert code == "the-code"
        self.sessions = getattr(self, "sessions", 0) + 1
        return {
            "session_id": f"s-{self.sessions}",
            "access": {"valid_until": self.valid_until},
            "accounts": [
                {
                    "uid": "u-1",
                    "identification_hash": "hash-giro",
                    "account_id": {"iban": "DE89370400440532013000"},
                    "currency": "EUR",
                    "name": "Girokonto",
                }
            ],
        }

    def transactions(self, uid, date_from):
        self.fetches.append(date_from)
        return list(self.data)

    def balances(self, uid):
        return [
            {"balance_type": "CLBD", "balance_amount": {"amount": "1234.56", "currency": "EUR"}}
        ]

    def request(self, method, path, body=None, query=None):
        return None


@pytest.fixture
def bank(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "enablebanking_redirect_url", "https://compass.example/finance"
    )
    fake = FakeBank()
    monkeypatch.setattr(finance, "enablebanking", fake)
    return fake


def connect(session, bank):
    url = finance.start_connect(session, "Volksbanken Raiffeisenbanken", "DE")
    assert url.startswith("https://bank.example/auth")
    return finance.finish_connect(session, "the-code", bank.state)


def test_token_is_signed_with_the_app_key(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    monkeypatch.setattr(get_settings(), "enablebanking_app_id", "app-123")
    monkeypatch.setattr(get_settings(), "enablebanking_private_key", base64.b64encode(pem).decode())
    token = enablebanking.token(now=1_700_000_000)
    head, claims, signature = token.split(".")

    def decode(part):
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))

    assert json.loads(decode(head)) == {"typ": "JWT", "alg": "RS256", "kid": "app-123"}
    assert json.loads(decode(claims))["exp"] - 1_700_000_000 == enablebanking.TOKEN_TTL
    key.public_key().verify(
        decode(signature), f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256()
    )


def test_connect_sync_and_no_duplicates(session, bank):
    bank.data = [
        tx("r1", 3, 54.20, "REWE Markt GmbH", "Kartenzahlung"),
        tx("r2", 2, 1200.00, "Universitaet", "Bezuege Oktober", debit=False),
        tx(None, 1, 4.50, "Bäckerei", None),
        tx(None, 1, 4.50, "Bäckerei", None),  # two identical rolls on a day stay two
        tx("r3", 1, 100.00, "Trade Republic Bank GmbH", "Sparplan"),
    ]
    conn = connect(session, bank)
    assert conn.status == "active"
    # 90 days at most, as the bank allows
    assert conn.valid_until - datetime.now(UTC) < timedelta(days=90)
    assert finance.sync(session) == {"Girokonto": 5}
    rows = session.query(BankTransaction).order_by(BankTransaction.id).all()
    assert [float(t.amount) for t in rows] == [-54.2, 1200.0, -4.5, -4.5, -100.0]
    assert [t.category for t in rows] == ["groceries", "income", None, None, "savings"]
    assert bank.fetches == [(TODAY - timedelta(days=365)).isoformat()]

    # Synced just now: the worker leaves it alone; forced it fetches again, without duplicates.
    assert finance.sync(session) == {}
    assert finance.sync(session, force=True) == {"Girokonto": 0}
    newest = TODAY - timedelta(days=1)
    assert bank.fetches[-1] == (newest - timedelta(days=finance.OVERLAP_DAYS)).isoformat()
    assert session.query(BankTransaction).count() == 5
    assert float(rows[0].account.balance) == 1234.56


def test_reconnecting_keeps_the_accounts(session, bank):
    first = connect(session, bank)
    second = connect(session, bank)
    assert first.status == "replaced" and second.status == "active"


def test_expired_consent_and_its_warning(session, bank, sent):
    conn = connect(session, bank)
    device(session)
    conn.valid_until = datetime.now(UTC) + timedelta(days=3)
    session.flush()
    assert notify.check_consent(session, at(TODAY, "10:00")) == 1
    assert sent[-1][1].title == "Bank access expires"
    assert notify.check_consent(session, at(TODAY, "11:00")) == 0
    conn.valid_until = datetime.now(UTC) - timedelta(minutes=1)
    finance.sync(session)
    assert conn.status == "expired"


def test_rules_sort_old_and_new_but_not_manual(session, bank):
    bank.data = [
        tx("a", 5, 12.00, "Kiosk Mueller", None),
        tx("b", 4, 8.00, "Kiosk Mueller", None),
    ]
    connect(session, bank)
    finance.sync(session)
    a, b = session.query(BankTransaction).order_by(BankTransaction.id).all()
    finance.set_category(session, a.id, "leisure")
    assert finance.add_rule(session, "Kiosk  MUELLER", "groceries") == 1
    assert (a.category, b.category) == ("leisure", "groceries")
    with pytest.raises(finance.FinanceError):
        finance.set_category(session, a.id, "luxus")


def test_months_budgets_and_recurring(client, session, bank):
    bank.data = [
        tx("s1", 62, 10.99, "Spotify AB", "Abo"),
        tx("s2", 31, 10.99, "Spotify AB", "Abo"),
        tx("s3", 1, 10.99, "Spotify AB", "Abo"),
        # PayPal pays everybody: grouped by the merchant in the purpose
        tx("p1", 61, 4.99, "PayPal Europe S.a.r.l.", "1031 PP.7342 Netflix ihr Einkauf"),
        tx("p2", 30, 4.99, "PayPal Europe S.a.r.l.", "1044 PP.9921 Netflix ihr Einkauf"),
        tx("p3", 0, 4.99, "PayPal Europe S.a.r.l.", "1057 PP.1180 Netflix ihr Einkauf"),
        # ended long ago
        tx("g1", 300, 9.00, "Gym", None),
        tx("g2", 270, 9.00, "Gym", None),
        tx("g3", 240, 9.00, "Gym", None),
        tx("e", 0, 30.00, "Lieferando", None),
        tx("u", 0, 200.00, "Eigenes Konto", "Umbuchung"),
        tx("i", 0, 900.00, "Arbeitgeber", "Lohn", debit=False),
    ]
    connect(session, bank)
    finance.sync(session)
    u = session.query(BankTransaction).filter_by(external_id="u").one()
    finance.set_category(session, u.id, "transfer")
    finance.set_budget(session, "eating_out", 25)
    with pytest.raises(finance.FinanceError):
        finance.set_budget(session, "income", 100)

    o = client.get("/api/finance/overview?months=3").json()
    month = o["months"][-1]
    assert month["income"] == 900
    assert month["by_category"]["eating_out"] == 30
    assert o["budgets"] == {"eating_out": 25}
    names = {r["name"]: r for r in o["recurring"]}
    assert set(names) == {"Spotify AB", "Netflix ihr Einkauf"}
    spotify = names["Spotify AB"]
    assert (spotify["monthly_cost"], spotify["interval"], spotify["category"]) == (
        10.99,
        "monthly",
        "subscriptions",
    )
    assert o["cash"] == 1234.56


def test_forecast_of_the_month_end(client, session, bank):
    bank.data = [
        tx("s1", 62, 10.99, "Spotify AB", "Abo"),
        tx("s2", 31, 10.99, "Spotify AB", "Abo"),
        tx("s3", 1, 10.99, "Spotify AB", "Abo"),
        tx("e", 0, 30.00, "Lieferando", None),
    ]
    connect(session, bank)
    finance.sync(session)
    f = finance.forecast(session, TODAY)
    assert f.month == f"{TODAY:%Y-%m}"
    assert f.cash == 1234.56
    # Only payments due before the month ends count, and the balance never gains income.
    assert all(r.next_date >= TODAY - timedelta(days=finance.LATE_DAYS) for r in f.due)
    assert f.projected_spending >= f.spent
    assert f.projected_cash <= f.cash
    got = client.get("/api/finance/forecast").json()
    assert got["cash"] == 1234.56 and got["days_left"] == f.days_left


def test_a_late_recurring_payment_still_counts_as_due(session, bank):
    # Rent every ~30 days, last 32 days ago: expected two days ago, not booked yet.
    bank.data = [
        tx("r1", 92, 700.00, "Vermieter", "Miete"),
        tx("r2", 62, 700.00, "Vermieter", "Miete"),
        tx("r3", 32, 700.00, "Vermieter", "Miete"),
    ]
    connect(session, bank)
    finance.sync(session)
    [rent] = finance.recurring(session, TODAY)
    assert rent.next_date < TODAY
    f = finance.forecast(session, TODAY)
    assert [r.name for r in f.due] == ["Vermieter"]
    assert f.recurring_due == 700.0


def test_depot_value_and_net_worth(client, session, bank):
    connect(session, bank)
    finance.sync(session)
    assert client.post("/api/finance/depot", json={"value": 5000}).status_code == 204
    future = (TODAY + timedelta(days=1)).isoformat()
    assert client.post("/api/finance/depot", json={"value": 1, "day": future}).status_code == 422
    o = client.get("/api/finance/overview").json()
    assert o["depot_value"] == 5000
    assert o["net_worth"] == 6234.56


def test_transaction_update_with_rule(client, session, bank):
    bank.data = [tx("a", 2, 7.0, "Kino Palast", None), tx("b", 1, 9.0, "Kino Palast", None)]
    connect(session, bank)
    finance.sync(session)
    [newest, older] = client.get("/api/finance/transactions?uncategorized=true").json()
    r = client.patch(
        f"/api/finance/transactions/{older['id']}",
        json={"category": "leisure", "rule_pattern": "kino palast"},
    )
    assert r.json()["rule_changed"] == 2
    assert client.get("/api/finance/transactions?category=leisure").json()[0]["id"] == newest["id"]


def test_status_without_enable_banking(client, session):
    s = client.get("/api/finance/status").json()
    assert s == {"configured": False, "connections": []}
    session.add(BankConnection(aspsp_name="X", aspsp_country="DE", state="st"))
    session.flush()
    r = client.post("/api/finance/connect/finish", json={"code": "c", "state": "nope"})
    assert r.status_code == 422


@pytest.fixture
def sent(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_public_key", "public")
    monkeypatch.setattr(settings, "vapid_private_key", "private")
    out = []
    monkeypatch.setattr(push, "_deliver", lambda sub, message: out.append((sub.endpoint, message)))
    return out


def test_rule_sets_and_currency(session, bank, monkeypatch):
    settings = get_settings()
    assert ("rewe", "groceries") in finance.rule_list(session)
    assert ("spotify", "subscriptions") in finance.rule_list(session)
    monkeypatch.setattr(settings, "finance_rule_sets", "")
    assert ("rewe", "groceries") not in finance.rule_list(session)
    assert ("spotify", "subscriptions") in finance.rule_list(session)

    assert finance.currency(session) == "EUR"
    connect(session, bank)
    session.scalar(select(BankAccount)).currency = "SEK"
    session.flush()
    assert finance.currency(session) == "SEK"


def test_transaction_splits_affect_monthly_categories_and_validate_sum(client, session, bank):
    from decimal import Decimal

    from app.models.finance import BankTransaction

    connect(session, bank)
    account = session.scalar(select(BankAccount))
    tx = BankTransaction(
        account_id=account.id,
        external_id="amazon-combo",
        booking_date=local_today(),
        amount=Decimal("-100.00"),
        counterparty="Amazon",
        purpose="Groceries and headphones",
        category="shopping",
        category_source="rule",
    )
    session.add(tx)
    session.commit()

    # Wrong sum is rejected.
    bad = client.put(
        f"/api/finance/transactions/{tx.id}/splits",
        json={
            "splits": [
                {"category": "shopping", "amount": 50},
                {"category": "groceries", "amount": 30},
            ]
        },
    )
    assert bad.status_code == 422

    # Valid split allocates 60 to shopping and 40 to groceries in monthly overview.
    ok = client.put(
        f"/api/finance/transactions/{tx.id}/splits",
        json={
            "splits": [
                {"category": "shopping", "amount": 60, "note": "headphones"},
                {"category": "groceries", "amount": 40, "note": "coffee"},
            ]
        },
    )
    assert ok.status_code == 200
    assert len(ok.json()["splits"]) == 2

    current = client.get("/api/finance/overview?months=1").json()["months"][-1]
    assert current["by_category"]["shopping"] == 60.0
    assert current["by_category"]["groceries"] == 40.0
    assert current["spending"] == 100.0

    # Filtering transactions by a split category finds the transaction.
    found = client.get("/api/finance/transactions?category=groceries").json()
    assert [t["id"] for t in found] == [tx.id]

    # Empty list clears splits.
    cleared = client.put(f"/api/finance/transactions/{tx.id}/splits", json={"splits": []})
    assert cleared.status_code == 200 and cleared.json()["splits"] == []


def test_savings_goals_crud(client, session):
    created = client.post(
        "/api/finance/goals",
        json={
            "name": "Emergency fund",
            "target_amount": 5000,
            "current_amount": 1200,
            "target_date": "2027-06-01",
        },
    )
    assert created.status_code == 201
    goal_id = created.json()["id"]
    assert created.json()["current_amount"] == 1200.0

    updated = client.patch(f"/api/finance/goals/{goal_id}", json={"current_amount": 2000})
    assert updated.status_code == 200 and updated.json()["current_amount"] == 2000.0

    listed = client.get("/api/finance/goals").json()
    assert [g["name"] for g in listed] == ["Emergency fund"]

    assert client.delete(f"/api/finance/goals/{goal_id}").status_code == 204
    assert client.get("/api/finance/goals").json() == []
