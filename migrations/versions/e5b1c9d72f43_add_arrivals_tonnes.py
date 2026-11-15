"""add price_observation.arrivals_tonnes (arrivals capture change)

Revision ID: e5b1c9d72f43
Revises: d4a7f8e63c21
Create Date: 2026-11-15 13:30:00.000000

Additive, reversible: one nullable column. Agmarknet co-reports market arrivals (metric
tonnes) in the same daily row as price; we now capture it going forward. NULL means the
source did not state it — never a guessed zero. No backfill: historical rows were captured
before arrivals were mapped, so they stay NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b1c9d72f43"
down_revision: str | Sequence[str] | None = "d4a7f8e63c21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "price_observation",
        sa.Column("arrivals_tonnes", sa.Numeric(precision=14, scale=3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("price_observation", "arrivals_tonnes")
