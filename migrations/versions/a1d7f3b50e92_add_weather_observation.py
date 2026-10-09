"""add weather_observation (WeatherUnion hyperlocal readings)

Revision ID: a1d7f3b50e92
Revises: f2c9a71d3e64
Create Date: 2026-10-09 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1d7f3b50e92"
down_revision: str | Sequence[str] | None = "f2c9a71d3e64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weather_observation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("locality", sa.String(length=120), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("humidity_pct", sa.Float(), nullable=True),
        sa.Column("wind_speed", sa.Float(), nullable=True),
        sa.Column("wind_direction", sa.Float(), nullable=True),
        sa.Column("rain_intensity", sa.Float(), nullable=True),
        sa.Column("rain_accumulation", sa.Float(), nullable=True),
        sa.Column("aqi_pm25", sa.Float(), nullable=True),
        sa.Column("aqi_pm10", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_weather_observation_locality", "weather_observation", ["locality"])
    op.create_index("ix_weather_observation_observed_at", "weather_observation", ["observed_at"])


def downgrade() -> None:
    op.drop_index("ix_weather_observation_observed_at", table_name="weather_observation")
    op.drop_index("ix_weather_observation_locality", table_name="weather_observation")
    op.drop_table("weather_observation")
