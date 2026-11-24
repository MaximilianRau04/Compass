"""finance savings goals and transaction splits

Revision ID: a1b2c3d4e5f6
Revises: 9b1f4d7c2e85
Create Date: 2026-11-24 13:35:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "9b1f4d7c2e85"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_transaction_splits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["transaction_id"], ["bank_transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bank_transaction_splits_transaction_id",
        "bank_transaction_splits",
        ["transaction_id"],
    )
    op.create_index(
        "ix_bank_transaction_splits_category",
        "bank_transaction_splits",
        ["category"],
    )

    op.create_table(
        "savings_goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("target_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("current_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("savings_goals")
    op.drop_index("ix_bank_transaction_splits_category", table_name="bank_transaction_splits")
    op.drop_index("ix_bank_transaction_splits_transaction_id", table_name="bank_transaction_splits")
    op.drop_table("bank_transaction_splits")
