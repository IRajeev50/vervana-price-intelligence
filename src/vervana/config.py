"""Application configuration, loaded from the environment.

Secrets never have real defaults and never live in the repo (Part 7). Anything
secret is Optional and defaults to None, so the app imports and runs in
development and tests without credentials — the code that *needs* a secret is
responsible for failing loudly when it is missing, not the config layer.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

# The whole system operates in Asia/Kolkata (Part 7). This is a hard constant,
# not a tunable, so it lives here as the single source of truth.
PROJECT_TIMEZONE = "Asia/Kolkata"


class Settings(BaseSettings):
    """Environment-driven settings.

    Loaded from process environment and, in development, from a local `.env`
    (which is git-ignored). See `.env.example` for the full key list.
    """

    model_config = SettingsConfigDict(
        env_prefix="VERVANA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Non-secret operational config (safe defaults) ---
    environment: str = "development"
    log_level: str = "INFO"

    # Timezone is fixed by policy; exposed as a field only so it is visible in
    # config dumps, never to be changed away from Asia/Kolkata.
    timezone: str = PROJECT_TIMEZONE

    # Comma-separated connector names to disable, e.g. "youtube,enam". A disabled
    # connector's run is a logged no-op — nothing else breaks (Part 4).
    disabled_connectors: str = ""

    # Public API (M8): comma-separated valid API keys, and a per-key rate limit.
    # A local default key keeps dev usable; production sets real keys via env.
    public_api_keys: str = "demo-key"
    public_api_rate_per_min: int = 60

    # --- Optional site access gate (deploy-only) ---
    # When BOTH are set, every HTML page requires HTTP basic auth. The JSON API
    # (/api/*) stays API-key gated and is not covered by this gate. Leave unset
    # in local dev so the dashboard stays frictionless.
    site_user: str | None = None
    site_password: str | None = None

    # --- Agmarknet 2.0 public API (api.agmarknet.gov.in) ---
    # Keyless: the 2.0 report endpoints are public (browser-like headers required).
    # The old data.gov.in resource went stale in Nov 2025, so the connector was
    # repointed here. Each ingest run walks back `agmarknet_lookback_days` days
    # (newest first) so a fresh deploy backfills a week, and transient failures are
    # retried with bounded exponential backoff. Raise the timeout locally (in .env)
    # only if captures keep timing out.
    agmarknet_timeout_seconds: float = 120.0
    agmarknet_max_retries: int = 4
    agmarknet_backoff_base_seconds: float = 2.0
    agmarknet_lookback_days: int = 7

    # --- Datastore ---
    # Defaults to a local SQLite file so nothing is required to import/run in dev
    # and tests. Production sets VERVANA_DATABASE_URL to the Postgres DSN.
    database_url: str = "sqlite:///vervana.dev.sqlite3"

    # --- Supply-side feeds (M11; safe defaults, secrets stay None) ---
    # Copernicus Data Space (Sentinel-2 NDVI fallback path): free OAuth client.
    cds_client_id: str | None = None
    cds_client_secret: str | None = None
    cds_token_url: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    cds_statistics_url: str = "https://sh.dataspace.copernicus.eu/api/v1/statistics"
    # IMD district rainfall: optional machine-readable CSV endpoint. The public
    # bulletin is a PDF; without this, use `vervana supply rainfall-import`.
    imd_district_rainfall_url: str | None = None
    # Google Agricultural Understanding (ALU/AMED)-partner access pending.
    # Endpoint URLs are not public; set them from the partner documentation when
    # access is granted. Empty => the scaffold reports "access pending" and
    # fetches nothing.
    google_agri_api_key: str | None = None
    google_alu_api_url: str | None = None
    google_amed_api_url: str | None = None

    # --- Secrets (no real defaults; must come from env when the feature needs them) ---

def get_settings() -> Settings:
    """Return a freshly-loaded Settings instance.

    Deliberately not cached: tests and CLI want to construct Settings against a
    controlled environment. Callers that want a process-wide singleton can hold
    onto the returned value themselves.
    """
    return Settings()

