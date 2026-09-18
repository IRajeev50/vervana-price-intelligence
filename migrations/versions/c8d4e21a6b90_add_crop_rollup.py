"""add crop_district_year_rollup

Revision ID: c8d4e21a6b90
Revises: b7e2c41f9a03
Create Date: 2026-09-18 11:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d4e21a6b90"
down_revision: str | Sequence[str] | None = "b7e2c41f9a03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crop_district_year_rollup",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state_name", sa.String(length=60), nullable=False),
        sa.Column("district_name", sa.String(length=60), nullable=False),
        sa.Column("year_label", sa.String(length=9), nullable=False),
        sa.Column("crop_name", sa.String(length=80), nullable=False),
        sa.Column("crop_type", sa.String(length=40), nullable=False),
        sa.Column("production_t", sa.Numeric(16, 3), nullable=True),
        sa.Column("area_ha", sa.Numeric(14, 2), nullable=True),
        sa.Column("yield_t_per_ha", sa.Numeric(12, 4), nullable=True),
        sa.Column("basis", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "state_name",
            "district_name",
            "year_label",
            "crop_name",
            name="uq_crop_rollup_row",
        ),
    )
    op.create_index(
        "ix_croprollup_state_district",
        "crop_district_year_rollup",
        ["state_name", "district_name"],
    )
    op.create_index("ix_croprollup_year", "crop_district_year_rollup", ["year_label"])


def downgrade() -> None:
    op.drop_index("ix_croprollup_year", table_name="crop_district_year_rollup")
    op.drop_index("ix_croprollup_state_district", table_name="crop_district_year_rollup")
    op.drop_table("crop_district_year_rollup")
