from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class BankConnection(TimestampMixin, Base):
    """A consent at a bank through Enable Banking (PSD2). It runs out after valid_until (at most
    180 days); then the user approves it again and the accounts carry on."""

    __tablename__ = "bank_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    aspsp_name: Mapped[str] = mapped_column(String(120))
    aspsp_country: Mapped[str] = mapped_column(String(2))
    # Set once the bank redirected back; before that the connection waits for it (state).
    session_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    state: Mapped[str | None] = mapped_column(String(64), unique=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|active|expired
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class BankAccount(TimestampMixin, Base):
    """An account at a bank. identification_hash stays the same across consents, uid does not."""

    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_connections.id", ondelete="SET NULL")
    )
    identification_hash: Mapped[str] = mapped_column(String(200), unique=True)
    uid: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    iban: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    balance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    connection: Mapped[BankConnection | None] = relationship()


class BankTransaction(Base):
    """A booked transaction. amount is signed: negative = money out."""

    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "external_id"),
        Index("ix_bank_transactions_booking_date", "booking_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(200))
    booking_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    counterparty: Mapped[str | None] = mapped_column(String(200))
    counterparty_iban: Mapped[str | None] = mapped_column(String(40))
    purpose: Mapped[str | None] = mapped_column(Text)
    # A category slug (app.services.finance.CATEGORIES); set by a rule, by hand or by an assistant.
    category: Mapped[str | None] = mapped_column(String(30), index=True)
    category_source: Mapped[str | None] = mapped_column(String(20))  # rule | manual | claude
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[BankAccount] = relationship()
    splits: Mapped[list["BankTransactionSplit"]] = relationship(
        cascade="all, delete-orphan", order_by="BankTransactionSplit.id"
    )


class BankTransactionSplit(Base):
    """Splits one bank transaction across multiple categories (e.g. a combined order).
    Amounts are positive and sum to abs(transaction.amount); the sign follows the transaction."""

    __tablename__ = "bank_transaction_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("bank_transactions.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(30), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    note: Mapped[str | None] = mapped_column(String(200))


class FinanceRule(TimestampMixin, Base):
    """Transactions whose counterparty or purpose contains the pattern get the category."""

    __tablename__ = "finance_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(100), unique=True)
    category: Mapped[str] = mapped_column(String(30))


class FinanceBudget(TimestampMixin, Base):
    """Monthly budget of a spending category."""

    __tablename__ = "finance_budgets"

    category: Mapped[str] = mapped_column(String(30), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))


class DepotValue(TimestampMixin, Base):
    """Value of the securities account on a day, entered by hand (Trade Republic has no API)."""

    __tablename__ = "depot_values"

    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))


class SavingsGoal(TimestampMixin, Base):
    """A medium- or long-term savings target (e.g. emergency fund, vacation)."""

    __tablename__ = "savings_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    current_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    target_date: Mapped[date | None] = mapped_column(Date)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
