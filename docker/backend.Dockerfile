FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq is needed by psycopg at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD sh -c 'curl -fsS http://localhost:${PORT:-8000}/api/health/live || exit 1'

CMD ["sh", "-c", "alembic upgrade head && python -m app.seed.seed --skip-forecast && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]