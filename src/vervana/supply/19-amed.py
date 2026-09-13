"""Google AMED seam (M11, SCAFFOLD): Agricultural Monitoring and Event Detection.

AMED builds on ALU: for identified fields it provides historical and current
in-season crop monitoring - chronologically ordered crop seasons with predicted
crop labels and sowing/harvest dates, refreshed roughly every 15 days
(https://agri.withgoogle.com/faq/). The platform use: supply TIMING. Sowing and
harvest event detection becomes `sowing_progress_pct` (production step) and
`harvest_progress_pct` (supply step), so an arrivals spike is visible in the
chain before it shows up in mandi quotes.

ACCESS STATE: same partner gate as ALU - scaffold, access pending. Every fetch
raises PartnerAccessPending; nothing is ingested or fabricated. The pure
mapping (`progress_signals`) is the real seam logic and is tested offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from vervana.config import Settings
from vervana.intelligence.signals import Signal, SignalStatus
from vervana.supply.scaffold import FeedStatus, PartnerFeed

AMED_DOCS_URL = "https://developers.google.com/agricultural-understanding"
AMED_PLATFORM_URL = "https://agri.withgoogle.com/"
SOURCE = "Google AMED (Agricultural Monitoring and Event Detection)"


class AmedClient(PartnerFeed):
    """SCAFFOLD client for the AMED API. Inert until partner access lands."""

    name = "google-amed"
    api_name = "Google AMED (Agricultural Monitoring and Event Detection)"
    docs_url = AMED_DOCS_URL

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)

    def _endpoint(self) -> str | None:
        return self._settings.google_amed_api_url

    def status(self) -> FeedStatus:
        return FeedStatus(
            name=self.name,
            title="Google AMED - sowing/harvest timing",
            layer="scaffold",
            configured=self.configured(),
            state=f"scaffold - {self.access_state()}",
            emits="sowing_progress_pct, harvest_progress_pct (production/supply steps)",
            hint="await partner approval, then set VERVANA_GOOGLE_AMED_API_URL + key",
            docs_url=self.docs_url,
        )

    def fetch_events(self, *, lat: float, lon: float, radius_m: int = 10000) -> list[dict]:
        """Field-level season events around a point. Raises until configured.

        Same contract as AluClient.fetch_crop_map: the request shape follows the
        partner documentation, which is not public until access is granted, so no
        response parsing is pretended here.
        """
        endpoint, key = self._require_access()
        import httpx  # local import: the scaffold must import cleanly with no network

        resp = httpx.get(
            endpoint,
            params={"location": f"{lat},{lon}", "radius_m": radius_m},
            headers={"X-Goog-Api-Key": key},
            timeout=60.0,
        )
        resp.raise_for_status()
        # TODO(partner-docs): validate the response schema against the AMED partner
        # documentation on first live call; do not guess field names before that.
        return [resp.json()]


@dataclass(frozen=True)
class FieldSeason:
    """One field's detected season, from AMED (or any event-detection source)."""

    zone: str
    crop: str
    area_ha: float
    sowing_date: date | None
    harvest_date: date | None


def progress_signals(
    fields: list[FieldSeason],
    expected_area_ha: dict[tuple[str, str], float],
    *,
    as_of: date,
    source: str = SOURCE,
    source_url: str | None = AMED_PLATFORM_URL,
) -> list[Signal]:
    """AMED field events -> OBSERVED sowing/harvest progress signals.

    Progress is area-based: sown (or harvested) area as % of the zone+crop's
    expected area this season. `expected_area_ha` keys are (zone, crop); a
    zone+crop with no honest expectation is skipped rather than divided by a
    guess. Fields with no detected event yet contribute area to neither side.
    """
    sown: dict[tuple[str, str], float] = {}
    harvested: dict[tuple[str, str], float] = {}
    for f in fields:
        key = (f.zone, f.crop)
        if f.sowing_date is not None and f.sowing_date <= as_of:
            sown[key] = sown.get(key, 0.0) + f.area_ha
        if f.harvest_date is not None and f.harvest_date <= as_of:
            harvested[key] = harvested.get(key, 0.0) + f.area_ha

    out: list[Signal] = []
    for key, expected in sorted(expected_area_ha.items()):
        if expected <= 0:
            continue
        zone, crop = key
        if key in sown:
            out.append(
                Signal(
                    kind="sowing_progress_pct",
                    region=zone,
                    on_date=as_of,
                    value_numeric=round(100.0 * sown[key] / expected, 2),
                    value_text=None,
                    status=SignalStatus.observed,
                    source=source,
                    source_url=source_url,
                    note=f"{crop}: {sown[key]:g} ha sown of {expected:g} ha expected",
                )
            )
        if key in harvested:
            out.append(
                Signal(
                    kind="harvest_progress_pct",
                    region=zone,
                    on_date=as_of,
                    value_numeric=round(100.0 * harvested[key] / expected, 2),
                    value_text=None,
                    status=SignalStatus.observed,
                    source=source,
                    source_url=source_url,
                    note=f"{crop}: {harvested[key]:g} ha harvested of {expected:g} ha expected",
                )
            )
    return out
