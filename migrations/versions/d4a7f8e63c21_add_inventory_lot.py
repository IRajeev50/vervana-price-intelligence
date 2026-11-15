"""add inventory_lot + lot_event (The Book, M17)

Revision ID: d4a7f8e63c21
Revises: c3f9a2d41e85
Create Date: 2026-11-15 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4a7f8e63c21"
down_revision: str | Sequence[str] | None = "c3f9a2d41e85"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_lot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("commodity_id", sa.Integer(), nullable=False),
        sa.Column("variety", sa.String(length=80), nullable=True),
        sa.Column("grade", sa.String(length=80), nullable=True),
        sa.Column("quantity_kg", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("purchase_price_paise_per_kg", sa.BigInteger(), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("warehouse", sa.String(length=160), nullable=False),
        sa.Column("warehouse_lat", sa.Float(), nullable=True),
        sa.Column("warehouse_lon", sa.Float(), nullable=True),
        sa.Column("intended_market_id", sa.Integer(), nullable=True),
        sa.Column("source_ref", sa.String(length=300), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["commodity_id"], ["commodity.id"]),
        sa.ForeignKeyConstraint(["intended_market_id"], ["market.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_lot_commodity_id", "inventory_lot", ["commodity_id"])

    op.create_table(
        "lot_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "ACQUIRED",
                "HELD",
                "RELEASED",
                "WRITTEN_OFF",
                name="loteventkind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("quantity_kg", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("price_paise_per_kg", sa.BigInteger(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lot_id"], ["inventory_lot.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lot_event_lot_id", "lot_event", ["lot_id"])


def downgrade() -> None:
    op.drop_index("ix_lot_event_lot_id", table_name="lot_event")
    op.drop_table("lot_event")
    op.drop_index("ix_inventory_lot_commodity_id", table_name="inventory_lot")
    op.drop_table("inventory_lot")
