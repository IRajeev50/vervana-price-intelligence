"""add supplier (commodity supplier organisations)

Revision ID: f2c9a71d3e64
Revises: e7b1c4f2a980
Create Date: 2026-09-24 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2c9a71d3e64"
down_revision: str | Sequence[str] | None = "e7b1c4f2a980"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "supplier",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("commodity", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("org_type", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=80), nullable=True),
        sa.Column("district", sa.String(length=80), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("contact_name", sa.String(length=160), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("commodity", "name", "state", name="uq_supplier_commodity_name_state"),
    )
    op.create_index("ix_supplier_commodity", "supplier", ["commodity"])
    op.create_index("ix_supplier_state", "supplier", ["state"])


def downgrade() -> None:
    op.drop_index("ix_supplier_state", table_name="supplier")
    op.drop_index("ix_supplier_commodity", table_name="supplier")
    op.drop_table("supplier")
