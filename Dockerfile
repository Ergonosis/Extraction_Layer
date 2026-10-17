# Multi-stage: build React portal, then run Flask API + static SPA on Cloud Run.
# Same-origin /api + cookies (portal axios baseURL is "/").

# ---- portal build ----
FROM node:22-bookworm-slim AS portal-build
WORKDIR /portal
COPY portal/package.json portal/package-lock.json ./
# Skip prepare/git hooks in the image build (no .git in context).
RUN npm pkg delete scripts.prepare && npm ci
COPY portal/ ./
RUN npm run build

# ---- API runtime ----
FROM python:3.12-slim-bookworm AS api
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FLASK_APP=api.app:create_app \
    PORTAL_STATIC_DIR=/app/portal_dist

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
COPY --from=portal-build /portal/dist ./portal_dist

# Non-root user for Cloud Run
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Default: serve API + SPA. Override command for migrate job:
#   flask db upgrade
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "120", "api.app:create_app()"]
