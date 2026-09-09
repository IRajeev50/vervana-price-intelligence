"""Config loads from env; secrets absent -> None, not a crash."""

from __future__ import annotations

import pytest

from vervana.config import PROJECT_TIMEZONE, Settings


def test_defaults_are_safe_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    # No VERVANA_* env vars and no .env: must still construct.
    for key in list(__import__("os").environ):
        if key.startswith("VERVANA_"):
            monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.data_gov_in_api_key is None  # secret absent -> None
    assert settings.timezone == PROJECT_TIMEZONE


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERVANA_ENVIRONMENT", "production")
    monkeypatch.setenv("VERVANA_DATA_GOV_IN_API_KEY", "secret-from-env")
    settings = Settings(_env_file=None)
    assert settings.environment == "production"
    assert settings.data_gov_in_api_key == "secret-from-env"


def test_timezone_is_pinned() -> None:
    # The timezone must not drift from Asia/Kolkata (Part 7).
    assert Settings(_env_file=None).timezone == "Asia/Kolkata"
