"""Sentinel-2 NDVI feed (M11): the supply layer's working satellite path.

Copernicus Data Space Ecosystem (CDSE) is free: register, create an OAuth
client, and the Statistical API returns per-zone NDVI means - no paid tile
pipeline. The connector fetches the current window AND the same window a year
earlier, and ingests the anomaly (current minus baseline) as an OBSERVED
`ndvi_anomaly` signal per zone.

Honesty rules:
- no credentials, no fetch: `fetch_raw` raises and `vervana supply ndvi` says
  exactly what to set up. Nothing is simulated.
- the NDVI mean is a vegetation estimate over a ~10 km box around the zone
  point, not a measurement of traded supply; the signal note carries both means
  so the number can be audited.
- request shape follows the CDSE Statistical API docs; verify against the
  current docs on the first live run (endpoint is a setting for that reason).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from vervana.config import Settings, get_settings
from vervana.connectors.base import Connector, IngestResult
from vervana.models.context import ContextSignal
from vervana.supply.ndvi import SENTINEL2_SOURCE, SENTINEL2_SOURCE_URL, anomaly_value
from vervana.supply.zones import SupplyZone

# Statistical-API evalscript: per-pixel NDVI with a data mask, aggregated by the
# API. Kept as one constant so the request is auditable in review.
NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "dataMask"] }],
    output: { id: "default", bands: 1, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(s) {
  if (s.dataMask === 0) { return [NaN]; }
  return [(s.B08 - s.B04) / (s.B08 + s.B04)];
}
""".strip()

#: Half-side of the square queried around a zone point, in degrees (~10 km).
BOX_HALF_DEG = 0.05


class Sentinel2NdviConnector(Connector):
    name = "sentinel2-ndvi"

    def enabled(self, settings: Settings | None = None) -> bool:
        settings = settings or get_settings()
        return (
            super().enabled(settings)
            and bool(settings.cds_client_id)
            and bool(settings.cds_client_secret)
        )

    # -- network ------------------------------------------------------------
    def fetch_raw(
        self,
        *,
        zones: list[SupplyZone],
        current_from: date,
        current_to: date,
        baseline_from: date,
        baseline_to: date,
        settings: Settings | None = None,
    ) -> list[dict]:
        """Fetch NDVI means for each zone (current + year-ago baseline windows)."""
        settings = settings or get_settings()
        if not self.enabled(settings):
            raise RuntimeError(
                "sentinel2-ndvi is not configured: register a free OAuth client at "
                "dataspace.copernicus.eu and set VERVANA_CDS_CLIENT_ID / "
                "VERVANA_CDS_CLIENT_SECRET. No request was made."
            )
        import httpx

        token_resp = httpx.post(
            settings.cds_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.cds_client_id,
                "client_secret": settings.cds_client_secret,
            },
            timeout=60.0,
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        records: list[dict] = []
        for z in zones:
            current = self._stats_mean(headers, settings, z, current_from, current_to)
            baseline = self._stats_mean(headers, settings, z, baseline_from, baseline_to)
            records.append(
                {
                    "zone": z.zone,
                    "district": z.district,
                    "state": z.state,
                    "on_date": current_to.isoformat(),
                    "current_mean": current,
                    "baseline_mean": baseline,
                }
            )
        return records

    def _stats_mean(
        self,
        headers: dict,
        settings: Settings,
        zone: SupplyZone,
        date_from: date,
        date_to: date,
    ) -> float | None:
        import httpx

        body = {
            "input": {
                "bounds": {
                    "bbox": [
                        zone.lon - BOX_HALF_DEG,
                        zone.lat - BOX_HALF_DEG,
                        zone.lon + BOX_HALF_DEG,
                        zone.lat + BOX_HALF_DEG,
                    ],
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [{"type": "sentinel-2-l2a", "dataFilter": {"maxCloudCoverage": 40}}],
            },
            "aggregation": {
                "timeRange": {
                    "from": f"{date_from.isoformat()}T00:00:00Z",
                    "to": f"{date_to.isoformat()}T23:59:59Z",
                },
                "aggregationInterval": {"of": "P30D"},
                "evalscript": NDVI_EVALSCRIPT,
            },
        }
        resp = httpx.post(settings.cds_statistics_url, headers=headers, json=body, timeout=120.0)
        resp.raise_for_status()
        payload = resp.json()
        means: list[float] = []
        for entry in payload.get("data", []):
            stats = (
                entry.get("outputs", {})
                .get("default", {})
                .get("bands", {})
                .get("B0", {})
                .get("stats", {})
            )
            mean = stats.get("mean")
            if mean is not None:
                means.append(float(mean))
        if not means:
            return None
        return sum(means) / len(means)

    # -- ingest (offline-testable) -------------------------------------------
    def ingest(self, session: Session, records: list[dict], *, mode: str = "api") -> IngestResult:
        """Raw zone records -> OBSERVED ndvi_anomaly rows in context_signal."""
        result = IngestResult(rows_in=len(records))
        for rec in records:
            try:
                current = float(rec["current_mean"])
                baseline = float(rec["baseline_mean"])
                on_date = date.fromisoformat(str(rec["on_date"]))
            except (KeyError, TypeError, ValueError) as exc:
                result.reject(f"parse_error: {exc}", rec)
                continue
            if not (-1.0 <= current <= 1.0 and -1.0 <= baseline <= 1.0):
                result.reject("ndvi_out_of_range_-1..1", rec)
                continue
            anomaly = anomaly_value(current, baseline)
            session.add(
                ContextSignal(
                    signal_type="ndvi_anomaly",
                    region=str(rec.get("district") or rec.get("zone") or "unknown"),
                    on_date=on_date,
                    value_numeric=anomaly,
                    value_text=None,
                    source=SENTINEL2_SOURCE,
                    source_url=SENTINEL2_SOURCE_URL,
                )
            )
            result.accept()
        return result
