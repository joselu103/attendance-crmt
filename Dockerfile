# syntax=docker/dockerfile:1
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.16 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["fastmcp", "run", "src/attendance_crmt/server.py", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
