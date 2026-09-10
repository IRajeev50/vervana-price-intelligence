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

    # --- Datastore ---
    # Defaults to a local SQLite file so nothing is required to import/run in dev
    # and tests. Production sets VERVANA_DATABASE_URL to the Postgres DSN.
    database_url: str = "sqlite:///vervana.dev.sqlite3"

    # --- Secrets (no real defaults; must come from env when the feature needs them) ---
    # data.gov.in API key for Agmarknet ingest (M2). Absent in dev/tests.
    data_gov_in_api_key: str | None = None


def get_settings() -> Settings:
    """Return a freshly-loaded Settings instance.

    Deliberately not cached: tests and CLI want to construct Settings against a
    controlled environment. Callers that want a process-wide singleton can hold
    onto the returned value themselves.
    """
    return Settings()
