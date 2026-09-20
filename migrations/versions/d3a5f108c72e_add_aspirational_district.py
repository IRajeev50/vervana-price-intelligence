"""add aspirational_district

Revision ID: d3a5f108c72e
Revises: c8d4e21a6b90
Create Date: 2026-09-20 09:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3a5f108c72e"
down_revision: str | Sequence[str] | None = "c8d4e21a6b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aspirational_district",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sno", sa.Integer(), nullable=False),
        sa.Column("state_name", sa.String(length=60), nullable=False),
        sa.Column("district_name", sa.String(length=80), nullable=False),
        sa.Column("district_key", sa.String(length=80), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_name", "district_name", name="uq_aspirational_state_district"),
    )
    op.create_index("ix_aspirational_state", "aspirational_district", ["state_name"])
    op.create_index(
        "ix_aspirational_district_district_key",
        "aspirational_district",
        ["district_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_aspirational_district_district_key", table_name="aspirational_district")
    op.drop_index("ix_aspirational_state", table_name="aspirational_district")
    op.drop_table("aspirational_district")
