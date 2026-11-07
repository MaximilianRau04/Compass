"""workout templates and removed mails

Revision ID: 5b2f8c1d9e47
Revises: c4d1a7e93b20
Create Date: 2026-11-07 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "5b2f8c1d9e47"
down_revision: Union[str, Sequence[str], None] = "c4d1a7e93b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workout_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "exercises",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workout_templates")),
        sa.UniqueConstraint("name", name=op.f("uq_workout_templates_name")),
    )
    op.add_column("emails", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    # A mail that became a task is handled: it leaves the triage list like a dismissed one.
    op.execute(
        "UPDATE emails SET dismissed_at = now() WHERE task_id IS NOT NULL AND dismissed_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("emails", "removed_at")
    op.drop_table("workout_templates")
