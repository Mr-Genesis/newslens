FROM python:3.12-slim

WORKDIR /app

# Make the `app` package importable for tools that don't put CWD on sys.path — notably the Alembic
# console script invoked by the start command (`alembic upgrade head`), whose migrations/env.py does
# `from app.config import settings`. Belt-and-suspenders with alembic.ini's prepend_sys_path.
ENV PYTHONPATH=/app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Render sets PORT env var; fallback to 8000 for local/docker-compose.
# Run migrations to head BEFORE serving so the schema can never drift behind the code (a failed
# migration intentionally blocks startup rather than serving a broken schema). Idempotent: a no-op
# once the DB is at head. NOTE: an existing DB that predates Alembic must be reconciled ONCE first
# (see DEPLOY.md → "Reconcile an existing (pre-Alembic) database") or this upgrade will fail on boot.
# docker-compose overrides this command for local dev (create_all owns the dev schema).
CMD sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
