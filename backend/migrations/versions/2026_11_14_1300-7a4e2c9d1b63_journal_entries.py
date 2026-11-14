"""journal entries: mood, energy and a text per day

Revision ID: 7a4e2c9d1b63
Revises: 3c7d9a1e5f21
Create Date: 2026-11-14 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7a4e2c9d1b63"
down_revision: Union[str, Sequence[str], None] = "3c7d9a1e5f21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("mood", sa.SmallInteger(), nullable=True),
        sa.Column("energy", sa.SmallInteger(), nullable=True),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
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
        sa.PrimaryKeyConstraint("local_date", name=op.f("pk_journal_entries")),
        sa.CheckConstraint("mood BETWEEN 1 AND 5", name=op.f("ck_journal_entries_mood")),
        sa.CheckConstraint("energy BETWEEN 1 AND 5", name=op.f("ck_journal_entries_energy")),
    )


def downgrade() -> None:
    op.drop_table("journal_entries")
