# Slim image for the Vervana app/CLI. Uses uv for reproducible installs.
FROM python:3.12-slim

# uv is copied from its official image — fast, no extra network install step.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better layer caching), then the source.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project --no-dev

COPY . .
RUN uv sync --no-dev

ENTRYPOINT ["uv", "run", "vervana"]
CMD ["healthcheck"]
