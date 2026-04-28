# Dhampur Green — Backend (sugar_india_services)

This document explains how to set up and run the backend services, how to run the ETL pipeline tests, and quick notes for the PM2-managed staging environment.

**Contents**

- Prerequisites
- Environment variables
- Setup (local)
- Run commands (API, Celery worker, Celery beat)
- Pipeline test runner (batch and per-business)
- Useful API endpoints and example requests
- PM2 (staging) quickstart
- Troubleshooting

Prerequisites
-------------

- Python 3.11+
- pip and virtualenv (recommended)
- PostgreSQL (for production/staging) or local DB for development
- Redis (for Celery broker & backend) — optional when using PM2 with host services
- Node.js + npm (for PM2 if you manage processes with PM2)

Environment variables (.env)
----------------------------

Place a `.env` file in `sugar_india_services/`. Important variables the app expects:

- `DATABASE_URL` — SQLAlchemy asyncpg URI (example):
  `postgresql+asyncpg://<user>:<password>@host.docker.internal:5432/dhampur_horeca`
- `CELERY_BROKER_URL` — e.g. `redis://redis:6379/0` or `redis://localhost:6379/0`
- `CELERY_BACKEND_URL` — e.g. `redis://redis:6379/1`
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` — for Agents/OpenAI usage
- `SERP_API_KEY`, `HUNTER_API_KEY`, `APOLLO_API_KEY`, `SNOV_CLIENT_ID`, `SNOV_CLIENT_SECRET` — pipeline provider keys
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` — for sending emails

There is an example `.env` already used by developers in this repo. Ensure credentials are correct for your environment.

Setup (local)
-------------

1. Create and activate a virtualenv:

```bash
cd sugar_india_services
python -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up the database and run migrations (Alembic):

```bash
# ensure DATABASE_URL points to a reachable Postgres instance
alembic upgrade head
```

Run commands (API, Celery worker, Celery beat)
----------------------------------------------

- Start the API (development):

```bash
# run directly with uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

- Start a Celery worker (one-off):

```bash
celery -A app.core.celery_app worker --loglevel=info --concurrency=2
```

- Start Celery beat (scheduler):

```bash
celery -A app.core.celery_app beat --loglevel=info
```

Notes:

- In production/staging the worker and beat are usually managed by process manager (PM2, systemd) or containers.
- Celery uses separate sessions in `app/db/session.py` (see `celery_session()`) to avoid cross-loop connection issues.

Pipeline test runner (batch and per-business)
---------------------------------------------

There is a standalone test script for running pipeline stages: `tests/test_pipeline.py`.

Usage examples:

- Run a single stage for a city (Stage 1 = extraction):

```bash
python tests/test_pipeline.py --stage 1 --city Gurgaon
```

- Run a stage end-to-end for a city:

```bash
python tests/test_pipeline.py --stage all --city Delhi
```

- Dry-run (skip real API calls; uses mock data):

```bash
python tests/test_pipeline.py --stage all --city Gurgaon --dry-run
```

- Per-business mode: extract once then run Stages 2→8 per-business before moving to the next business

```bash
python tests/test_pipeline.py --mode per-business --city Gurgaon
```

The script prints stage outputs and can call the agents bridge. It is useful for local development and debugging pipeline stages.

Useful API endpoints
--------------------

The backend exposes API routes under the `/api` prefix (see `app/api/` for router details). Key endpoints:

- `GET /health` — simple health check (200 OK)
- `GET /api/leads` — list leads (pagination + filters)
- `GET /api/leads/{id}` — lead details
- `POST /api/leads/{id}/generate-email` — generate an outreach email for the lead (Stage 7)
- `POST /api/outreach/send` and related outreach endpoints — manage bulk send and polling tasks (see `app/api/outreach.py`)
- `GET /api/dashboard/stats` — dashboard KPIs (used by frontend)

Example: generate an email for a lead

```bash
curl -X POST "http://localhost:8001/api/leads/<lead_id>/generate-email" -H "Content-Type: application/json"
```

Replace `<lead_id>` with a real lead UUID.

PM2 (staging) quickstart
------------------------

This repo includes a `ecosystem.config.js` to run the API + Celery worker + beat using PM2.

1. Install PM2 globally:

```bash
npm install -g pm2
```

2. Start processes (in `sugar_india_services/`):

```bash
pm2 start ecosystem.config.js
pm2 ls
pm2 logs horeca-api --lines 200
```

3. Stop / restart / delete:

```bash
pm2 stop ecosystem.config.js
pm2 restart horeca-api
pm2 delete ecosystem.config.js
```

Notes:

- The PM2 ecosystem script sources `.env` and activates `venv` if present. Ensure `.env` is present and `venv` is created (see Setup above).
- The `ecosystem.config.js` creates a `logs/` directory and sets permissive permissions so PM2 can write logs.

Data Export -> (local) - Import -> (staging server)
------------------------

1. python scripts/export_and_stage.py --export
2. python scripts/export_and_stage.py --import --folder exports/2026-04-28_08-56-07

Troubleshooting
---------------

- Database connection problems:

  - If connecting from containers, use `host.docker.internal` on macOS or the host's IP on Linux. Ensure `DATABASE_URL` includes the port and password.
  - Confirm Postgres is running and listening (`pg_isready`, `psql`). Update `postgresql.conf` (`listen_addresses`) and `pg_hba.conf` as needed.
- Celery "Future attached to a different loop" errors:

  - Celery tasks should use `celery_session()` (NullPool) when running tasks that call async DB code. See `app/db/session.py`.
- PM2 permission errors writing logs:

  - Ensure `logs/` exists and is writable by the PM2 user. The PM2 ecosystem creates and chmods the `logs/` folder on process start.

If you want, I can:

- Update this README with more endpoint examples (specific request/response shapes) after you point to which endpoints you want detailed, or
- Create a short `DEPLOY.md` describing how to promote code from staging (PM2) to a production environment.
