"""Google Flood Hub seam (M15, SCAFFOLD): riverine flood RISK OVERLAY.

Flood Hub forecasts **riverine** flooding (CWC's 1,000+ gauges across India),
NOT rainfall, NOT urban waterlogging, NOT crop stress. In this platform it is a
**tail-event risk overlay** shown beside the price band / margin watch and emitted
as a labelled chain signal - it is **never a price-band feature** and never an
input to a forecast. It is labelled riverine-only everywhere it appears.

ACCESS STATE: the Flood Forecasting API is free but API-key + activation gated
(waitlist), and access is NOT granted yet. Until `VERVANA_FLOODHUB_API_KEY` is
set, every fetch raises PartnerAccessPending and NOTHING is ingested or
fabricated. When live, gauges are discovered by AREA (`SearchGaugesByArea`) over
each belt - no gauge IDs are hardcoded - then `QueryGaugeForecasts` gives each
gauge's `FloodStatus.severity`. The severity -> overlay mapping below is the real,
model-independent seam logic and is fully tested offline against the verified
`Severity` enum.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from vervana.config import Settings
from vervana.supply.scaffold import FeedStatus, PartnerAccessPending, PartnerFeed

FLOODHUB_DOCS_URL = "https://sites.research.google/floods/"
SOURCE = "Google Flood Hub (riverine flood forecast)"

# Verified Severity enum (floodforecasting.v1), ordered least -> most severe.
# UNKNOWN / UNSPECIFIED are deliberately absent: an un-modelled or unknown gauge is
# ignored, NEVER counted as "no flooding".
_SEVERITY_ORDER = {"NO_FLOODING": 0, "ABOVE_NORMAL": 1, "SEVERE": 2, "EXTREME": 3}


def severity_is_risk(severity: str) -> bool:
    """True when a verified riverine severity rises above normal (ABOVE_NORMAL/SEVERE/
    EXTREME). UNKNOWN/unspecified is False — never counted as risk, never as "no flooding"."""
    return _SEVERITY_ORDER.get(severity, 0) >= _SEVERITY_ORDER["ABOVE_NORMAL"]


@dataclass(frozen=True)
class GaugeFloodStatus:
    """One gauge's current riverine flood status - the neutral shape the overlay
    consumes. Populated from a FloodStatus message once access lands."""

    gauge_id: str
    severity: str  # one of the verified Severity enum values
    trend: str  # RISE | FALL | NO_CHANGE | ""
    issued_time: datetime | None
    valid_from: date | None
    valid_to: date | None
    has_model: bool = True


@dataclass(frozen=True)
class FloodOverlay:
    """A zone's riverine tail-risk flag: the worst modelled severity in the window."""

    zone: str
    severity: str
    trend: str
    issued_time: datetime | None
    valid_from: date | None
    valid_to: date | None

    @property
    def is_risk(self) -> bool:
        """True when the overlay rises above normal (ABOVE_NORMAL/SEVERE/EXTREME)."""
        return _SEVERITY_ORDER.get(self.severity, 0) >= _SEVERITY_ORDER["ABOVE_NORMAL"]


def overlay_from_statuses(zone: str, statuses: list[GaugeFloodStatus]) -> FloodOverlay | None:
    """Reduce a zone's gauges to its worst MODELLED riverine severity. Pure.

    Gauges without a model, or with UNKNOWN/unspecified severity, are ignored (not
    treated as "no flooding"). Returns None when the zone has no usable gauge, so a
    gap is distinguishable from a genuine NO_FLOODING reading.
    """
    usable = [s for s in statuses if s.has_model and s.severity in _SEVERITY_ORDER]
    if not usable:
        return None
    worst = max(usable, key=lambda s: _SEVERITY_ORDER[s.severity])
    return FloodOverlay(
        zone=zone,
        severity=worst.severity,
        trend=worst.trend,
        issued_time=worst.issued_time,
        valid_from=worst.valid_from,
        valid_to=worst.valid_to,
    )


class FloodHubClient(PartnerFeed):
    """SCAFFOLD client for the Flood Forecasting API. Inert until access lands."""

    name = "google-floodhub"
    api_name = "Google Flood Hub (riverine flood forecast)"
    docs_url = FLOODHUB_DOCS_URL

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)

    def _endpoint(self) -> str | None:
        return self._settings.floodhub_api_url  # host is always known

    def _api_key(self) -> str | None:
        return self._settings.floodhub_api_key

    def access_state(self) -> str:
        if not self._api_key():
            return "access pending (waitlist) - set VERVANA_FLOODHUB_API_KEY once approved"
        return "ready"

    def status(self) -> FeedStatus:
        return FeedStatus(
            name=self.name,
            title="Google Flood Hub - riverine flood overlay",
            layer="scaffold",
            configured=self.configured(),
            state=f"scaffold - {self.access_state()}",
            emits="flood_risk_riverine overlay (tail-risk, NOT a band feature, NOT rainfall)",
            hint="join the Flood Forecasting API waitlist, then set VERVANA_FLOODHUB_API_KEY",
            docs_url=self.docs_url,
        )

    def fetch_overlays(self, zones) -> list[FloodOverlay]:
        """Discover gauges by area for each zone and reduce to a riverine overlay.

        Raises PartnerAccessPending until the API key is configured. When live:
        SearchGaugesByArea over each zone's area -> QueryGaugeForecasts ->
        GaugeFloodStatus -> overlay_from_statuses. No gauge IDs are hardcoded; the
        field mapping is confirmed against the live schema on first access.
        """
        self._require_access()
        raise PartnerAccessPending(  # pragma: no cover - unreachable without a key
            "Flood Hub access is configured but the gauge discovery + FloodStatus "
            "mapping must be confirmed against the live API before the first pull. "
            "See docs/SUPPLY.md; nothing was fetched or fabricated."
        )
