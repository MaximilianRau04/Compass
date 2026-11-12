"""credentials for sign-ins (microsoft mail)

Revision ID: 8e3a6f2b1c90
Revises: 5b2f8c1d9e47
Create Date: 2026-11-12 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e3a6f2b1c90"
down_revision: Union[str, Sequence[str], None] = "5b2f8c1d9e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credentials",
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("secret", sa.Text(), nullable=True),
        sa.Column("pending", sa.Text(), nullable=True),
        sa.Column("signed_in_as", sa.String(length=320), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
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
        sa.PrimaryKeyConstraint("name", name=op.f("pk_credentials")),
    )


def downgrade() -> None:
    op.drop_table("credentials")
