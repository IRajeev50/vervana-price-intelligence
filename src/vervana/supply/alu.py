"""Google ALU seam (M11, SCAFFOLD): Agricultural Landscape Understanding.

ALU provides field boundaries, landscape/crop type and field acreage, queried by
geographic location; its data refreshes roughly every 6 months
(https://agri.withgoogle.com/faq/). The platform use: a live district crop map -
which crop, on how much area, per season - which becomes `acreage_change_pct`
signals for the production step of the intelligence chain.

ACCESS STATE: partner access is requested, not granted (Google's interest form,
review measured in weeks). The public docs (docs_url below) describe the API's
shape but not a callable endpoint, so the endpoint setting stays empty until the
partner documentation lands. Until then every fetch raises PartnerAccessPending
and nothing is ingested or fabricated. The pure mapping below
(`acreage_change_signals`) is the real seam logic and is fully tested offline.
"""

from __future__ import annotations

from dataclasses import dataclass

from vervana.config import Settings
from vervana.intelligence.signals import Signal, SignalStatus
from vervana.supply.scaffold import FeedStatus, PartnerFeed

ALU_DOCS_URL = "https://developers.google.com/agricultural-understanding"
ALU_PLATFORM_URL = "https://agri.withgoogle.com/"
SOURCE = "Google ALU (Agricultural Landscape Understanding)"


class AluClient(PartnerFeed):
    """SCAFFOLD client for the ALU API. Inert until partner access lands."""

    name = "google-alu"
    api_name = "Google ALU (Agricultural Landscape Understanding)"
    docs_url = ALU_DOCS_URL

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)

    def _endpoint(self) -> str | None:
        return self._settings.google_alu_api_url

    def status(self) -> FeedStatus:
        return FeedStatus(
            name=self.name,
            title="Google ALU - district crop map",
            layer="scaffold",
            configured=self.configured(),
            state=f"scaffold - {self.access_state()}",
            emits="acreage_change_pct (production step)",
            hint="await partner approval, then set VERVANA_GOOGLE_ALU_API_URL + key",
            docs_url=self.docs_url,
        )

    def fetch_crop_map(self, *, lat: float, lon: float, radius_m: int = 10000) -> list[dict]:
        """Fields/crop map around a point. Raises until access is configured.

        When partner docs land, this issues GET {endpoint} with the API key and
        the location query exactly as the docs specify; the response schema is
        partner-confidential until then, so no parser is pretended here.
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
        # TODO(partner-docs): validate the response schema against the ALU partner
        # documentation on first live call; do not guess field names before that.
        return [resp.json()]


@dataclass(frozen=True)
class CropArea:
    """One zone+crop+season area figure, from ALU (or any crop-map source)."""

    zone: str
    crop: str
    season: str  # like-for-like season label, e.g. "kharif-2026"
    area_ha: float


def acreage_change_signals(
    current: list[CropArea],
    previous: list[CropArea],
    *,
    on_date,
    source: str = SOURCE,
    source_url: str | None = ALU_PLATFORM_URL,
) -> list[Signal]:
    """ALU crop map -> OBSERVED acreage_change_pct signals.

    Pairs each current-season zone+crop area with the same zone+crop in the
    previous like-for-like season. Unpaired rows are skipped (no comparison is
    better than an invented one). A zero previous area is skipped: a percent
    change against nothing would be a lie with decimals.
    """
    prev_by_key = {(p.zone, p.crop): p.area_ha for p in previous}
    out: list[Signal] = []
    for c in current:
        prev = prev_by_key.get((c.zone, c.crop))
        if prev is None or prev <= 0:
            continue
        change = round(100.0 * (c.area_ha - prev) / prev, 2)
        out.append(
            Signal(
                kind="acreage_change_pct",
                region=c.zone,
                on_date=on_date,
                value_numeric=change,
                value_text=None,
                status=SignalStatus.observed,
                source=source,
                source_url=source_url,
                note=(f"{c.crop} {c.season}: {c.area_ha:g} ha vs {prev:g} ha previous season"),
            )
        )
    return out
