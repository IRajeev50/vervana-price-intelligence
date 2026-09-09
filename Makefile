# Vervana — one-command developer surface.
# Every target below works from a clean clone with only `uv` installed.
# `make test` runs offline (no network, no Docker) per the build spec.

.PHONY: help setup test lint fmt fmt-check risks up down clean hooks

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the venv (Python 3.12 managed by uv) and install deps
	uv sync

test:  ## Run the offline test suite
	uv run pytest

lint:  ## Lint with ruff
	uv run ruff check .

fmt:  ## Auto-format with ruff
	uv run ruff format .

fmt-check:  ## Check formatting without changing files (used in CI)
	uv run ruff format --check .

risks:  ## Regenerate docs/RISK_REGISTER.md from seed + code tags
	uv run python scripts/gen_risk_register.py

hooks:  ## Install pre-commit git hooks
	uv run pre-commit install

up:  ## Start local dev stack (app + postgres) via Docker Compose
	docker compose up -d

down:  ## Stop the local dev stack
	docker compose down

clean:  ## Remove caches and the dev SQLite db
	rm -rf .pytest_cache .ruff_cache **/__pycache__ vervana.dev.sqlite3
