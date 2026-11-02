# API-only image for Cloud Run. SPA is deployed separately to Firebase Hosting.
# Same-origin cookies work via Hosting /api/** rewrite to this service.

FROM python:3.12-slim-bookworm AS api
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FLASK_APP=api.app:create_app \
    PORTAL_STATIC_DIR=

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY migrations ./migrations
COPY microsoft ./microsoft
COPY plaid ./plaid

# Non-root user for Cloud Run
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Override command for migrate job: flask db upgrade
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "120", "api.app:create_app()"]
