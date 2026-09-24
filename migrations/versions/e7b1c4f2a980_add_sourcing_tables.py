"""add sourcing tables (buyer, supplier_contact)

Revision ID: e7b1c4f2a980
Revises: d3a5f108c72e
Create Date: 2026-09-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b1c4f2a980"
down_revision: str | Sequence[str] | None = "d3a5f108c72e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "supplier_contact",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("contact_name", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["market.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supplier_contact_market_id", "supplier_contact", ["market_id"])
    op.create_table(
        "buyer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("city", sa.String(length=80), nullable=True),
        sa.Column("state", sa.String(length=80), nullable=True),
        sa.Column("commodities", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=160), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("buyer")
    op.drop_index("ix_supplier_contact_market_id", table_name="supplier_contact")
    op.drop_table("supplier_contact")
