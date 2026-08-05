FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.8.3 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --uid 10001 amath
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=amath:amath pyproject.toml alembic.ini ./
COPY --chown=amath:amath alembic ./alembic
COPY --chown=amath:amath src ./src
USER amath

CMD ["sh", "-c", "alembic upgrade head && python -m amath_bot.app"]
