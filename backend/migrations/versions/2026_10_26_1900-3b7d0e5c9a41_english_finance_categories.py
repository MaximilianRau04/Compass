"""english finance categories

Revision ID: 3b7d0e5c9a41
Revises: e51251ecb026
Create Date: 2026-10-26 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3b7d0e5c9a41"
down_revision: Union[str, Sequence[str], None] = "e51251ecb026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old German slug -> English slug (app.services.finance.CATEGORIES).
RENAMED = {
    "wohnen": "housing",
    "lebensmittel": "groceries",
    "essen": "eating_out",
    "mobilitaet": "transport",
    "abos": "subscriptions",
    "versicherung": "insurance",
    "gesundheit": "health",
    "freizeit": "leisure",
    "bildung": "education",
    "bargeld": "cash",
    "gebuehren": "fees",
    "sonstiges": "other",
    "einkommen": "income",
    "sparen": "savings",
    "umbuchung": "transfer",
}
TABLES = ("bank_transactions", "finance_rules", "finance_budgets")


def _rename(mapping: dict[str, str]) -> None:
    for table in TABLES:
        for old, new in mapping.items():
            op.execute(
                sa.text(f"UPDATE {table} SET category = :new WHERE category = :old").bindparams(
                    old=old, new=new
                )
            )


def upgrade() -> None:
    """Upgrade schema."""
    _rename(RENAMED)


def downgrade() -> None:
    """Downgrade schema."""
    _rename({new: old for old, new in RENAMED.items()})
