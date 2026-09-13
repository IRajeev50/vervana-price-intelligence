"""Partner-access scaffolds (M11): the seam for feeds we want but cannot call yet.

A scaffold is a REAL integration seam, not a demo: it knows its API, its auth
model, and exactly which platform signals it will emit - but until partner
access and credentials exist, every fetch raises PartnerAccessPending and
NOTHING is ingested. It never fabricates a response, never returns sample data
as if live, and its status everywhere (CLI, web) is "scaffold - access
pending", never "connected".
"""

from __future__ import annotations

from dataclasses import dataclass

from vervana.config import Settings, get_settings


class PartnerAccessPending(RuntimeError):
    """Raised when a partner-gated feed is called before access/credentials exist."""


@dataclass(frozen=True)
class FeedStatus:
    """One supply feed's honest state, shared by the CLI and the web UI."""

    name: str  # machine name, e.g. "google-alu"
    title: str  # human name, e.g. "Google ALU (crop map)"
    layer: str  # "fallback" (works today) | "scaffold" (partner-gated)
    configured: bool  # credentials/endpoint present
    state: str  # one-line honest state, e.g. "scaffold - access pending"
    emits: str  # signal kinds it produces
    hint: str  # exact next step to light it up
    docs_url: str | None = None


class PartnerFeed:
    """Base for partner-gated feeds (Google ALU/AMED). Never fakes a response."""

    name = "partner-feed"
    api_name = "partner API"
    docs_url: str | None = None

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    # Subclasses report which settings gate them.
    def _endpoint(self) -> str | None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _api_key(self) -> str | None:
        return self._settings.google_agri_api_key

    def access_state(self) -> str:
        """Honest access state: endpoint pending -> credentials pending -> ready."""
        if not self._endpoint():
            return "endpoint pending (set from partner docs once access is granted)"
        if not self._api_key():
            return "credentials pending (VERVANA_GOOGLE_AGRI_API_KEY not set)"
        return "ready"

    def configured(self) -> bool:
        return self.access_state() == "ready"

    def _require_access(self) -> tuple[str, str]:
        """Return (endpoint, api_key) or raise. The single gate every fetch goes through."""
        endpoint, key = self._endpoint(), self._api_key()
        if not endpoint or not key:
            raise PartnerAccessPending(
                f"{self.api_name} is a SCAFFOLD: partner access is not granted/configured "
                f"yet ({self.access_state()}). No request was made and no data was "
                f"fabricated. See docs/SUPPLY.md."
            )
        return endpoint, key
