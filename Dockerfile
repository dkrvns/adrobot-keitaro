FROM ghcr.io/astral-sh/uv:0.11.1@sha256:fc93e9ecd7218e9ec8fba117af89348eef8fd2463c50c13347478769aaedd0ce AS uv
FROM python:3.14-slim-bookworm@sha256:3fe1a0b6c2d6b2ebb572906cdabeca75aeb558c0c17db5ffefbcf8094871c32b AS base

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./

FROM base AS development
RUN uv sync --locked --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
COPY tests ./tests
RUN uv sync --locked
ENV UV_NO_SYNC=1

FROM base AS runtime
RUN uv sync --locked --no-dev --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN uv sync --locked --no-dev --no-editable \
    && useradd --uid 10001 --create-home adrobot
ENV UV_NO_SYNC=1 PYTHONDONTWRITEBYTECODE=1
USER 10001
CMD ["uv", "run", "uvicorn", "adrobot.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "50", "--no-proxy-headers"]

FROM development AS browser
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
