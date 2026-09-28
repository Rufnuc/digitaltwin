# DigitalTwin API — production image (FastAPI + uvicorn on Postgres).
FROM python:3.11-slim

# System deps kept minimal; psycopg[binary] ships its own libpq.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for layer caching.
COPY requirements-prod.txt ./
RUN pip install --upgrade pip && pip install -r requirements-prod.txt

# App code (see .dockerignore for what's excluded).
COPY . .

# Object-storage dir for uploaded documents (ephemeral on most PaaS — see runbook
# for the note about moving to S3-style storage for durable attachments).
RUN mkdir -p /app/storage

# The platform provides $PORT. On boot: migrate, then (best-effort, idempotent)
# create the first OWNER from OWNER_EMAIL/OWNER_PASSWORD if the DB has no users, then serve.
ENV PORT=8000 ENVIRONMENT=production
CMD ["sh", "-c", "alembic upgrade head && { python -m scripts.create_owner || true; } && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
