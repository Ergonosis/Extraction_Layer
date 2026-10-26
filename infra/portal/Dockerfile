ARG PYTHON_VERSION=3

FROM ghcr.io/astral-sh/uv:0.12 AS uv

FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080 \
    FLASK_APP=src.api.app:create_app

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock uv.toml ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "120", "src.api.app:create_app()"]
