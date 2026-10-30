"""deadline feeds and study mail category

Revision ID: 7c2e91d4a6b3
Revises: 3b7d0e5c9a41
Create Date: 2026-10-30 19:30:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7c2e91d4a6b3"
down_revision: Union[str, Sequence[str], None] = "3b7d0e5c9a41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE task_source ADD VALUE IF NOT EXISTS 'feed'")
    op.execute("UPDATE emails SET category = 'study' WHERE category = 'uni'")


def downgrade() -> None:
    """Downgrade schema. Postgres cannot drop an enum value, so "feed" stays."""
    op.execute("UPDATE emails SET category = 'uni' WHERE category = 'study'")
