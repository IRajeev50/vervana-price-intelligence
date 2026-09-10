"""add intelligence_report

Revision ID: a7f3c9d21b45
Revises: 9b31808e6ada
Create Date: 2026-09-10 17:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import vervana.db.base  # custom column types (e.g. UTCDateTime) referenced in migrations

# revision identifiers, used by Alembic.
revision: str = "a7f3c9d21b45"
down_revision: str | Sequence[str] | None = "9b31808e6ada"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intelligence_report",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("commodity", sa.String(length=120), nullable=False),
        sa.Column("made_at", vervana.db.base.UTCDateTime(), nullable=False),
        sa.Column("horizon_label", sa.String(length=40), nullable=False),
        sa.Column("verdict", sa.String(length=40), nullable=False),
        sa.Column("n_observed", sa.Integer(), nullable=False),
        sa.Column("n_simulated", sa.Integer(), nullable=False),
        sa.Column("n_missing", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intelligence_report_commodity", "intelligence_report", ["commodity"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_report_commodity", table_name="intelligence_report")
    op.drop_table("intelligence_report")
