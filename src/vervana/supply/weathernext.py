"""Google WeatherNext 3 seam (M13, SCAFFOLD): forward weather forecast feed.

WeatherNext 3 is DeepMind's global AI weather model (hourly init, 15-day horizon,
64-member ensemble). We do NOT pull the raw ensemble: BigQuery publishes
precomputed surface percentiles (p10/p25/p50/p75/p90), so the platform queries
only the handful of grid points nearest our origin belts and keeps the data tiny.
The feed emits `weather_forecast` ROWS - precip p10/p50/p90 and tmax/tmin per zone
per valid date - which are the forward-supply inputs the Phase-2 price band will
try to beat the anchor with. A forecast is NOT a price and NOT a chain signal: it
lives in its own table and is never joined into price_observation.

ACCESS STATE: allowlist access is NOT granted yet. Until the GCP project + the
BigQuery percentiles table + credentials are configured, every fetch raises
PartnerAccessPending and NOTHING is ingested or fabricated - identical honesty to
the ALU/AMED scaffolds. The raw BigQuery-row -> ForecastPoint mapping depends on
the exact published column names, which we will confirm against the live BigQuery
catalog on first access (we do not guess them here). The DAILY AGGREGATION below
(`aggregate_daily`) is the real, model-independent seam logic and is fully tested
offline on fixtures.

Honest caveat on the band: a daily precip percentile here is the SUM of that
percentile's hourly values over the day. That is an approximation of a true daily
percentile (it assumes hourly independence; real precip is temporally
correlated), so the daily p10/p90 is a usable band, not an exact daily quantile.
The band only reaches the serving path in Phase 2 if it beats the anchor on the
walk-forward backtest - this approximation is tested there, never assumed good.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from vervana.config import Settings
from vervana.supply.scaffold import FeedStatus, PartnerAccessPending, PartnerFeed

WEATHERNEXT_DOCS_URL = "https://deepmind.google/science/weathernext/"
SOURCE = "Google DeepMind WeatherNext 3 (BigQuery percentiles)"


@dataclass(frozen=True)
class ForecastPoint:
    """One zone's forecast for one valid hour - the neutral internal shape the
    daily aggregation consumes. Precip percentiles and 2m temperature are hourly.
    Populated from a BigQuery row once access lands (mapping confirmed then)."""

    zone: str
    model_run_time: datetime  # UTC - the forecast initialization
    valid_time: datetime  # UTC - the hour this forecast is for
    precip_mm_p10: float
    precip_mm_p50: float
    precip_mm_p90: float
    temp_c: float | None


@dataclass(frozen=True)
class ForecastRecord:
    """One daily forecast row per zone per valid date - what gets stored."""

    zone: str
    model_run_time: datetime
    valid_date: date
    lead_days: int
    precip_mm_p10: float
    precip_mm_p50: float
    precip_mm_p90: float
    tmax_c: float | None
    tmin_c: float | None


def aggregate_daily(points: list[ForecastPoint]) -> list[ForecastRecord]:
    """Aggregate hourly forecast points into one daily record per (zone, date).

    Pure and side-effect free. Daily precip per percentile = SUM of that
    percentile's hourly values (see module caveat); tmax/tmin = max/min of the
    hourly 2m temperature (None when no hour reported a temperature). lead_days is
    valid_date minus the model run's date, clamped at 0. Output is sorted by
    (zone, valid_date) for stable storage and testing.
    """
    buckets: dict[tuple[str, date], list[ForecastPoint]] = {}
    for p in points:
        buckets.setdefault((p.zone, p.valid_time.date()), []).append(p)

    records: list[ForecastRecord] = []
    for (zone, valid_date), pts in buckets.items():
        run = min(p.model_run_time for p in pts)
        temps = [p.temp_c for p in pts if p.temp_c is not None]
        lead = (valid_date - run.date()).days
        records.append(
            ForecastRecord(
                zone=zone,
                model_run_time=run,
                valid_date=valid_date,
                lead_days=max(lead, 0),
                precip_mm_p10=round(sum(p.precip_mm_p10 for p in pts), 3),
                precip_mm_p50=round(sum(p.precip_mm_p50 for p in pts), 3),
                precip_mm_p90=round(sum(p.precip_mm_p90 for p in pts), 3),
                tmax_c=max(temps) if temps else None,
                tmin_c=min(temps) if temps else None,
            )
        )
    records.sort(key=lambda r: (r.zone, r.valid_date))
    return records


class WeatherNextClient(PartnerFeed):
    """SCAFFOLD client for WeatherNext 3 on BigQuery. Inert until access lands."""

    name = "google-weathernext"
    api_name = "Google WeatherNext 3 (BigQuery)"
    docs_url = WEATHERNEXT_DOCS_URL

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)

    # --- access gating (BigQuery, not the ALU/AMED key) ---
    def _endpoint(self) -> str | None:
        s = self._settings
        if s.weathernext_gcp_project and s.weathernext_bq_dataset and s.weathernext_bq_table:
            return (
                f"{s.weathernext_gcp_project}."
                f"{s.weathernext_bq_dataset}.{s.weathernext_bq_table}"
            )
        return None

    def _api_key(self) -> str | None:
        # A service-account JSON path (or ADC via GOOGLE_APPLICATION_CREDENTIALS).
        import os

        return self._settings.weathernext_credentials_path or os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )

    def access_state(self) -> str:
        if not self._endpoint():
            return (
                "access pending (allowlist) - set VERVANA_WEATHERNEXT_GCP_PROJECT / "
                "_BQ_DATASET / _BQ_TABLE once approved"
            )
        if not self._api_key():
            return (
                "credentials pending - set VERVANA_WEATHERNEXT_CREDENTIALS_PATH or "
                "GOOGLE_APPLICATION_CREDENTIALS"
            )
        return "ready"

    def status(self) -> FeedStatus:
        return FeedStatus(
            name=self.name,
            title="Google WeatherNext 3 - forward weather forecast",
            layer="scaffold",
            configured=self.configured(),
            state=f"scaffold - {self.access_state()}",
            emits="weather_forecast rows (precip p10/p50/p90, tmax/tmin per zone/date)",
            hint="join the WeatherNext allowlist, then set VERVANA_WEATHERNEXT_* in .env",
            docs_url=self.docs_url,
        )

    def fetch_forecasts(self, zones) -> list[ForecastRecord]:
        """Fetch + daily-aggregate forecasts for the given zones.

        Raises PartnerAccessPending until access is configured. When live, this
        queries the BigQuery percentiles table for ONLY these zones' nearest grid
        points, maps each row to a ForecastPoint (column mapping confirmed against
        the live catalog on first access - not guessed here), then returns
        aggregate_daily(points). No request is made and no row is invented while
        access is pending.
        """
        self._require_access()
        raise PartnerAccessPending(  # pragma: no cover - unreachable without creds
            "WeatherNext access is configured but the BigQuery row->ForecastPoint "
            "mapping must be confirmed against the live catalog before the first "
            "pull. See docs/SUPPLY.md; nothing was fetched or fabricated."
        )
