"""weekdays a workout template is planned on

Revision ID: 3c7d9a1e5f21
Revises: 8e3a6f2b1c90
Create Date: 2026-11-14 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3c7d9a1e5f21"
down_revision: Union[str, Sequence[str], None] = "8e3a6f2b1c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workout_templates",
        sa.Column(
            "weekdays",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("workout_templates", "weekdays")
