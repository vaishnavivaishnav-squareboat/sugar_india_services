# Archived: sugar_india_services/Dockerfile
# Original Dockerfile archived before removal

# ─────────────────────────────────────────────────────────────────────────────
# Dhampur Green HORECA — Backend Dockerfile
# Supports three runtime targets:
#   api     → uvicorn (default)
#   worker  → celery worker
#   beat    → celery beat
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# Install dumb-init (clean signal handling) + system deps for psycopg2 / C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    dumb-init \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer — copy requirements first)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose API port
EXPOSE 8001

# Health check against FastAPI's root or a dedicated /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Use dumb-init to handle OS signals correctly (Ctrl-C, SIGTERM from Docker)
ENTRYPOINT ["dumb-init", "--"]

# Default: run FastAPI via uvicorn
# Override CMD in docker-compose for worker / beat targets
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
