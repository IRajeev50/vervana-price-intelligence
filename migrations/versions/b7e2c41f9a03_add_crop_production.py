"""add crop_production

Revision ID: b7e2c41f9a03
Revises: a7f3c9d21b45
Create Date: 2026-09-18 10:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import vervana.db.base  # custom column types (e.g. UTCDateTime) referenced in migrations

# revision identifiers, used by Alembic.
revision: str = "b7e2c41f9a03"
down_revision: str | Sequence[str] | None = "a7f3c9d21b45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crop_production",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("year_label", sa.String(length=9), nullable=False),
        sa.Column("state_name", sa.String(length=60), nullable=False),
        sa.Column("district_name", sa.String(length=60), nullable=False),
        sa.Column("crop_name", sa.String(length=80), nullable=False),
        sa.Column("crop_type", sa.String(length=40), nullable=False),
        sa.Column("season", sa.String(length=20), nullable=False),
        sa.Column("area_ha", sa.Numeric(14, 2), nullable=True),
        sa.Column("production_t", sa.Numeric(16, 3), nullable=True),
        sa.Column("yield_t_per_ha", sa.Numeric(12, 4), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("imported_at", vervana.db.base.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "year_label",
            "state_name",
            "district_name",
            "crop_name",
            "season",
            name="uq_crop_production_row",
        ),
        sa.CheckConstraint(
            "length(trim(source_url)) > 0", name="ck_cropprod_source_url_present"
        ),
    )
    op.create_index(
        "ix_cropprod_district_year", "crop_production", ["district_name", "year_label"]
    )
    op.create_index("ix_cropprod_crop", "crop_production", ["crop_name"])


def downgrade() -> None:
    op.drop_index("ix_cropprod_crop", table_name="crop_production")
    op.drop_index("ix_cropprod_district_year", table_name="crop_production")
    op.drop_table("crop_production")
