"""add flood_overlay (Flood Hub riverine tail-risk rows)

Revision ID: c3f9a2d41e85
Revises: b2e8c4a19f07
Create Date: 2026-11-14 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f9a2d41e85"
down_revision: str | Sequence[str] | None = "b2e8c4a19f07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flood_overlay",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("zone", sa.String(length=60), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("trend", sa.String(length=20), nullable=False),
        sa.Column("issued_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("zone", "issued_time", name="uq_flood_overlay_zone_issued"),
    )
    op.create_index("ix_flood_overlay_zone", "flood_overlay", ["zone"])


def downgrade() -> None:
    op.drop_index("ix_flood_overlay_zone", table_name="flood_overlay")
    op.drop_table("flood_overlay")
