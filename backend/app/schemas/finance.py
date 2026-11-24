from datetime import date, datetime

from pydantic import BaseModel, Field


class ConnectionRead(BaseModel):
    id: int
    aspsp_name: str
    status: str = Field(description="active or expired (approve again)")
    valid_until: datetime | None
    last_sync_at: datetime | None
    last_error: str | None


class FinanceStatus(BaseModel):
    configured: bool = Field(description="Enable Banking keys and redirect URL are set")
    connections: list[ConnectionRead]


class BankRead(BaseModel):
    name: str
    country: str
    logo: str | None = None


class ConnectStart(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


class ConnectUrl(BaseModel):
    url: str


class ConnectFinish(BaseModel):
    code: str = Field(min_length=1, max_length=2000)
    state: str = Field(min_length=1, max_length=64)


class SyncResult(BaseModel):
    new_transactions: dict[str, int]


class AccountRead(BaseModel):
    id: int
    name: str
    iban: str | None
    currency: str
    balance: float | None
    balance_at: datetime | None


class MonthRead(BaseModel):
    month: str
    income: float
    spending: float
    saved: float
    by_category: dict[str, float]
    uncategorized: int


class RecurringRead(BaseModel):
    name: str
    category: str | None
    amount: float
    interval: str
    monthly_cost: float
    last_date: date
    next_date: date
    count: int


class ForecastRead(BaseModel):
    month: str
    days_left: int
    spent: float = Field(description="Spent so far this month")
    recurring_due: float = Field(description="Recurring payments still due this month")
    variable_per_day: float = Field(description="Other spending per day, last 3 full months")
    projected_spending: float
    cash: float
    projected_cash: float = Field(description="At the month's end, without income to come")
    due: list[RecurringRead]


class DepotRead(BaseModel):
    date: date
    value: float


class FinanceOverview(BaseModel):
    months: list[MonthRead]
    budgets: dict[str, float]
    accounts: list[AccountRead]
    cash: float
    depot: list[DepotRead]
    depot_value: float | None
    invested: float = Field(description="Money moved to the securities account in the data")
    net_worth: float
    recurring: list[RecurringRead]
    categories: list[str]
    spending_categories: list[str]


class TransactionSplitRead(BaseModel):
    id: int
    category: str
    amount: float
    note: str | None = None


class TransactionSplitInput(BaseModel):
    category: str = Field(max_length=30)
    amount: float = Field(gt=0, le=100_000_000)
    note: str | None = Field(default=None, max_length=200)


class SplitsUpdate(BaseModel):
    splits: list[TransactionSplitInput] = Field(max_length=20)


class TransactionRead(BaseModel):
    id: int
    account: str
    booking_date: date
    amount: float
    currency: str
    counterparty: str | None
    purpose: str | None
    category: str | None
    category_source: str | None
    splits: list[TransactionSplitRead] = []


class TransactionUpdate(BaseModel):
    category: str = Field(max_length=30)
    # Also sort future (and unsorted past) transactions containing this text.
    rule_pattern: str | None = Field(default=None, min_length=3, max_length=100)


class TransactionUpdated(BaseModel):
    transaction: TransactionRead
    rule_changed: int = Field(description="Other transactions the new rule sorted")


class BudgetSet(BaseModel):
    amount: float = Field(ge=0, le=100000, description="Per month, 0 removes it")


class DepotLog(BaseModel):
    value: float = Field(ge=0, le=100_000_000)
    day: date | None = None


class SavingsGoalRead(BaseModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    target_date: date | None
    archived: bool


class SavingsGoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: float = Field(gt=0, le=100_000_000)
    current_amount: float = Field(default=0.0, ge=0, le=100_000_000)
    target_date: date | None = None


class SavingsGoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: float | None = Field(default=None, gt=0, le=100_000_000)
    current_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    target_date: date | None = None
    archived: bool | None = None
