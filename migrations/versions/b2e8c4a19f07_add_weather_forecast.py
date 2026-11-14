"""add weather_forecast (WeatherNext 3 daily forecast rows)

Revision ID: b2e8c4a19f07
Revises: a1d7f3b50e92
Create Date: 2026-11-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2e8c4a19f07"
down_revision: str | Sequence[str] | None = "a1d7f3b50e92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weather_forecast",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("zone", sa.String(length=60), nullable=False),
        sa.Column("model_run_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_date", sa.Date(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("precip_mm_p10", sa.Float(), nullable=True),
        sa.Column("precip_mm_p50", sa.Float(), nullable=True),
        sa.Column("precip_mm_p90", sa.Float(), nullable=True),
        sa.Column("tmax_c", sa.Float(), nullable=True),
        sa.Column("tmin_c", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "zone", "model_run_time", "valid_date", name="uq_weather_forecast_run_valid"
        ),
    )
    op.create_index("ix_weather_forecast_zone", "weather_forecast", ["zone"])
    op.create_index("ix_weather_forecast_valid_date", "weather_forecast", ["valid_date"])


def downgrade() -> None:
    op.drop_index("ix_weather_forecast_valid_date", table_name="weather_forecast")
    op.drop_index("ix_weather_forecast_zone", table_name="weather_forecast")
    op.drop_table("weather_forecast")
