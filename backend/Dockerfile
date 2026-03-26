FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Render sets PORT env var; fallback to 8000 for local/docker-compose
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
