"""feeds added in the app

Revision ID: 8e1899ac2f4c
Revises: 7c2e91d4a6b3
Create Date: 2026-10-31 18:41:33.776527

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e1899ac2f4c"
down_revision: Union[str, Sequence[str], None] = "7c2e91d4a6b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("stream", sa.String(length=10), nullable=True),
        sa.Column("deadline_pattern", sa.Text(), nullable=True),
        sa.Column("area", sa.String(length=40), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feeds")),
        sa.UniqueConstraint("kind", "name", name=op.f("uq_feeds_kind")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("feeds")
