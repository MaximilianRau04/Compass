from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.config import get_settings
from app.models.finance import BankConnection, BankTransaction, SavingsGoal
from app.schemas.finance import (
    AccountRead,
    BankRead,
    BudgetSet,
    ConnectFinish,
    ConnectionRead,
    ConnectStart,
    ConnectUrl,
    DepotLog,
    DepotRead,
    FinanceOverview,
    FinanceStatus,
    ForecastRead,
    MonthRead,
    PositionRead,
    PositionSet,
    RecurringRead,
    SavingsGoalCreate,
    SavingsGoalRead,
    SavingsGoalUpdate,
    SplitsUpdate,
    SyncResult,
    TransactionRead,
    TransactionSplitRead,
    TransactionUpdate,
    TransactionUpdated,
)
from app.services import enablebanking, finance

router = APIRouter(prefix="/finance", tags=["finance"])


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, enablebanking.BankingError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    return HTTPException(422, str(exc))


def connection_read(c: BankConnection) -> ConnectionRead:
    return ConnectionRead(
        id=c.id,
        aspsp_name=c.aspsp_name,
        status=c.status,
        valid_until=c.valid_until,
        last_sync_at=c.last_sync_at,
        last_error=c.last_error,
    )


def transaction_read(t: BankTransaction) -> TransactionRead:
    return TransactionRead(
        id=t.id,
        account=t.account.name,
        booking_date=t.booking_date,
        amount=float(t.amount),
        currency=t.currency,
        counterparty=t.counterparty,
        purpose=t.purpose,
        category=t.category,
        category_source=t.category_source,
        splits=[
            TransactionSplitRead(id=s.id, category=s.category, amount=float(s.amount), note=s.note)
            for s in t.splits
        ],
    )


def savings_goal_read(g: SavingsGoal) -> SavingsGoalRead:
    return SavingsGoalRead(
        id=g.id,
        name=g.name,
        target_amount=float(g.target_amount),
        current_amount=float(g.current_amount),
        target_date=g.target_date,
        archived=g.archived,
    )


@router.get("/status", response_model=FinanceStatus)
def finance_status(session: SessionDep):
    o = finance.overview(session, 1)
    return FinanceStatus(
        configured=enablebanking.configured()
        and bool(get_settings().enablebanking_redirect_url.strip()),
        connections=[connection_read(c) for c in o.connections],
    )


@router.get("/banks", response_model=list[BankRead])
def banks(
    q: Annotated[str, Query(max_length=80)] = "",
    country: Annotated[str | None, Query(pattern=r"^[A-Z]{2}$")] = None,
):
    """Banks Enable Banking can connect, filtered by name."""
    try:
        found = enablebanking.aspsps(country or get_settings().finance_country)
    except enablebanking.BankingError as exc:
        raise _fail(exc) from exc
    words = q.lower().split()
    return [
        BankRead(name=b["name"], country=b["country"], logo=b.get("logo"))
        for b in found
        if all(w in b["name"].lower() for w in words)
    ][:30]


@router.post("/connect", response_model=ConnectUrl)
def connect(data: ConnectStart, session: SessionDep):
    """Start connecting a bank; the browser goes to the returned URL to approve."""
    try:
        url = finance.start_connect(
            session, data.name, data.country or get_settings().finance_country
        )
    except (finance.FinanceError, enablebanking.BankingError) as exc:
        raise _fail(exc) from exc
    session.commit()
    return ConnectUrl(url=url)


@router.post("/connect/finish", response_model=SyncResult)
def connect_finish(data: ConnectFinish, session: SessionDep):
    """The bank sent the browser back with a code: store the accounts and fetch them."""
    try:
        finance.finish_connect(session, data.code, data.state)
        session.commit()
        result = finance.sync(session, force=True)
    except (finance.FinanceError, enablebanking.BankingError) as exc:
        session.rollback()
        raise _fail(exc) from exc
    session.commit()
    return SyncResult(new_transactions=result)


@router.post("/connections/{connection_id}/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(connection_id: int, session: SessionDep):
    try:
        finance.disconnect(session, connection_id)
    except finance.FinanceError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    session.commit()


@router.post("/sync", response_model=SyncResult)
def sync(session: SessionDep):
    result = finance.sync(session, force=True)
    session.commit()
    return SyncResult(new_transactions=result)


@router.get("/overview", response_model=FinanceOverview)
def overview(session: SessionDep, months: Annotated[int, Query(ge=1, le=24)] = 6):
    o = finance.overview(session, months)
    depot = o.depot_value
    return FinanceOverview(
        months=[MonthRead(**m.__dict__) for m in o.months],
        budgets=o.budgets,
        accounts=[
            AccountRead(
                id=a.id,
                name=a.name,
                iban=a.iban,
                currency=a.currency,
                balance=float(a.balance) if a.balance is not None else None,
                balance_at=a.balance_at,
            )
            for a in o.balances
        ],
        cash=round(o.cash, 2),
        depot=[DepotRead(date=d.local_date, value=float(d.value)) for d in o.depot],
        depot_value=depot,
        invested=o.invested,
        net_worth=round(o.cash + (depot or 0), 2),
        recurring=[RecurringRead(**r.__dict__) for r in o.recurring],
        positions=[
            PositionRead(
                symbol=p.symbol,
                name=p.name,
                quantity=float(p.quantity),
                price=float(p.price) if p.price is not None else None,
            )
            for p in o.positions
        ],
        categories=list(finance.CATEGORIES),
        spending_categories=list(finance.SPENDING),
    )


@router.get("/forecast", response_model=ForecastRead)
def forecast(session: SessionDep):
    """The end of this month: spent so far, recurring payments still due, other spending at the
    pace of the last three full months, and the balance left without income still to come."""
    f = finance.forecast(session)
    return ForecastRead(
        **{k: v for k, v in f.__dict__.items() if k != "due"},
        due=[RecurringRead(**r.__dict__) for r in f.due],
    )


@router.get("/transactions", response_model=list[TransactionRead])
def transactions(
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=800)] = 60,
    category: str | None = None,
    uncategorized: bool = False,
    q: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
):
    found = finance.transactions(session, days, category, uncategorized, q, limit)
    return [transaction_read(t) for t in found]


@router.patch("/transactions/{transaction_id}", response_model=TransactionUpdated)
def update_transaction(transaction_id: int, data: TransactionUpdate, session: SessionDep):
    try:
        changed = (
            finance.add_rule(session, data.rule_pattern, data.category) if data.rule_pattern else 0
        )
        t = finance.set_category(session, transaction_id, data.category)
    except finance.FinanceError as exc:
        raise _fail(exc) from exc
    session.commit()
    return TransactionUpdated(transaction=transaction_read(t), rule_changed=changed)


@router.put("/budgets/{category}", status_code=status.HTTP_204_NO_CONTENT)
def set_budget(category: str, data: BudgetSet, session: SessionDep):
    try:
        finance.set_budget(session, category, data.amount)
    except finance.FinanceError as exc:
        raise _fail(exc) from exc
    session.commit()


@router.post("/depot", status_code=status.HTTP_204_NO_CONTENT)
def log_depot(data: DepotLog, session: SessionDep):
    try:
        finance.log_depot(session, data.value, data.day)
    except finance.FinanceError as exc:
        raise _fail(exc) from exc
    session.commit()


@router.put("/positions/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def set_position(symbol: str, data: PositionSet, session: SessionDep):
    try:
        finance.set_position(session, symbol, data.quantity)
    except finance.FinanceError as exc:
        raise _fail(exc) from exc
    session.commit()


@router.put("/transactions/{transaction_id}/splits", response_model=TransactionRead)
def update_splits(transaction_id: int, data: SplitsUpdate, session: SessionDep):
    try:
        t = finance.set_splits(
            session,
            transaction_id,
            [(s.category, s.amount, s.note) for s in data.splits],
        )
    except finance.FinanceError as exc:
        raise _fail(exc) from exc
    session.commit()
    return transaction_read(t)


@router.get("/goals", response_model=list[SavingsGoalRead])
def list_goals(session: SessionDep, include_archived: bool = False):
    return [savings_goal_read(g) for g in finance.list_savings_goals(session, include_archived)]


@router.post("/goals", response_model=SavingsGoalRead, status_code=status.HTTP_201_CREATED)
def create_goal(data: SavingsGoalCreate, session: SessionDep):
    try:
        goal = finance.create_savings_goal(
            session,
            data.name,
            data.target_amount,
            data.current_amount,
            data.target_date,
        )
    except finance.FinanceError as exc:
        raise _fail(exc) from exc
    session.commit()
    return savings_goal_read(goal)


@router.patch("/goals/{goal_id}", response_model=SavingsGoalRead)
def update_goal(goal_id: int, data: SavingsGoalUpdate, session: SessionDep):
    changes = {k: getattr(data, k) for k in data.model_fields_set}
    try:
        goal = finance.update_savings_goal(session, goal_id, **changes)
    except finance.FinanceError as exc:
        raise _fail(exc) from exc
    session.commit()
    return savings_goal_read(goal)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, session: SessionDep):
    try:
        finance.delete_savings_goal(session, goal_id)
    except finance.FinanceError as exc:
        raise _fail(exc) from exc
    session.commit()
