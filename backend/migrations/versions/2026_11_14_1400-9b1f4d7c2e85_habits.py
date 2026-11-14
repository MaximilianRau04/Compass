"""habits and their daily checks

Revision ID: 9b1f4d7c2e85
Revises: 7a4e2c9d1b63
Create Date: 2026-11-14 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b1f4d7c2e85"
down_revision: Union[str, Sequence[str], None] = "7a4e2c9d1b63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "habits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("rule", sa.String(length=30), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_habits")),
    )
    op.create_table(
        "habit_checks",
        sa.Column("habit_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["habit_id"],
            ["habits.id"],
            name=op.f("fk_habit_checks_habit_id_habits"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("habit_id", "local_date", name=op.f("pk_habit_checks")),
    )


def downgrade() -> None:
    op.drop_table("habit_checks")
    op.drop_table("habits")
