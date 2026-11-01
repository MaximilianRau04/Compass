"""notes search in english too

Revision ID: c4d1a7e93b20
Revises: 8e1899ac2f4c
Create Date: 2026-11-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4d1a7e93b20"
down_revision: Union[str, Sequence[str], None] = "8e1899ac2f4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BOTH = (
    "setweight(to_tsvector('german', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('german', coalesce(body, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(body, '')), 'B') || "
    "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body, ''))"
)
GERMAN = (
    "setweight(to_tsvector('german', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('german', coalesce(body, '')), 'B') || "
    "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body, ''))"
)


def _search_column(expression: str) -> None:
    """Postgres cannot change the expression of a generated column, so it is added anew."""
    op.drop_index("ix_notes_search", table_name="notes", postgresql_using="gin")
    op.drop_column("notes", "search")
    op.add_column(
        "notes",
        sa.Column(
            "search",
            postgresql.TSVECTOR(),
            sa.Computed(expression, persisted=True),
            nullable=False,
        ),
    )
    op.create_index("ix_notes_search", "notes", ["search"], postgresql_using="gin")


def upgrade() -> None:
    """Upgrade schema."""
    _search_column(BOTH)


def downgrade() -> None:
    """Downgrade schema."""
    _search_column(GERMAN)
