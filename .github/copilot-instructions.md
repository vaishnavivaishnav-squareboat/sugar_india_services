# Copilot Instructions — Dhampur Green HORECA Lead Intelligence

## Monorepo layout
Two sibling packages at the repo root:
- `sugar_india_services/` — FastAPI + Celery backend (Python)
- `sugar_india/` — React + Vite + Tailwind + shadcn/ui frontend

## Backend: `sugar_india_services/`

### Package structure (refactored — no flat files)
| Path | Purpose |
|---|---|
| `main.py` | FastAPI entry point; imports `app.api.api_router`; runs `Base.metadata.create_all` on startup |
| `app/db/orm.py` | Canonical ORM models: `Lead`, `OutreachEmail`, `City`, `PipelineRun`, `Segment`, `Contact` |
| `app/db/session.py` | `engine`, `AsyncSessionLocal`, `Base`, `get_db()` dependency — import these, never redefine |
| `app/core/config.py` | All env vars loaded once from `.env`; import typed constants from here |
| `app/api/` | One router per entity (`lead.py`, `city.py`, `segment.py`, `contact.py`, `outreach.py`, `dashboard.py`); aggregated in `app/api/__init__.py` as `api_router` with `/api` prefix |
| `app/pipelines/stages.py` | 8 async ETL stage functions (~1 000 lines) |
| `app/agents/` | OpenAI Agents SDK wrappers: `agents/` (Agent definitions), `runners/`, `tools/`, `bridge.py` (stage 2/5/7 entry), `pipeline.py` (demo script) |
| `app/utils/genai.py` | `call_genai(prompt, force_json)` — Gemini `gemini-2.0-flash` with round-robin key rotation |
| `app/utils/scoring.py` | `calculate_lead_score(data)` → `(score, priority, reasoning)`; `make_lead_obj()` |
| `app/core/celery_app.py` | Celery app `horeca_pipeline`; **one city per invocation** (round-robin by `last_processed_at ASC`) |
| `app/core/cron.py` | Weekly cron script; **all active cities per run**; uses `fcntl` lock to prevent overlap |
| `app/prompts/` | Prompt builder functions for Gemini (business_intelligence, contact_extraction, email_generation, lead_qualify, lead_email_api) |
| `app/schemas/` | Pydantic request/response models |

### Two parallel automation paths
1. **Celery path** (`app/core/celery_app.py`) — Celery beat triggers `run_city_pipeline` weekly; selects ONE city round-robin; bridges sync→async via `asyncio.run()`.
2. **Cron path** (`app/core/cron.py`) — direct Python script; processes ALL active cities; run manually or via `crontab`.

### 8-stage ETL pipeline (`app/pipelines/stages.py`)
1. `extract_business_data` — SerpAPI Google Maps; runs in `ThreadPoolExecutor(max_workers=4)` to avoid blocking the async loop
2. `ai_process_business_data` — Gemini classifies menus, sugar signals, estimates monthly kg
3. `apply_kpi_filtering` — composite score threshold rejection
4. `deduplicate_leads` — fuzzy name + geo dedup + DB cross-check
5. `enrich_contacts` — SerpAPI + Gemini AI contact discovery
6. `enrich_emails` — Hunter.io + Apollo.io email lookup
7. `generate_personalized_emails` — Gemini outreach email generation
8. `store_leads_and_emails` — persist to DB

`HORECA_QUERY_MAP` in `stages.py` controls which segments run — currently **only `Bakery`** is active; all others are commented out.

### AI layer: two models in use
- **Gemini** (`app/utils/genai.py`) — pipeline stages 2, 5, 7; `force_json=True` sets `response_mime_type: application/json`; keys rotated via `itertools.cycle` over `GENAI_API_KEYS`
- **OpenAI Agents SDK** (`app/agents/`) — wraps same pipeline logic in typed `Agent` objects; **`import app.services.openai_client` must appear before any agent import** to register the async client and disable tracing

### Key conventions
- `Lead.id` = `uuid4` string; `City`, `PipelineRun`, `Contact` use integer PK + ULID surrogate
- Scoring thresholds: `ai_score` ≥ 70 → `High`, ≥ 40 → `Medium`, else `Low`
- Routes use `async with AsyncSessionLocal() as session:` directly — not the `get_db()` FastAPI dependency
- `model_to_dict()` in `app/utils/__init__.py` serializes any ORM model to dict (ISO-formats datetimes)
- New ORM models → `app/db/orm.py` + Alembic migration; never use `create_all` in production
- `Lead.highlights`, `offerings`, `dining_options`, `highlight_sugar_signals` are `JSON` columns (arrays)

## Required env vars
```
DATABASE_URL           # asyncpg PostgreSQL URL
GENAI_API_KEYS         # comma-separated Gemini API keys
GOOGLE_PLACES_API_KEY  # Google Places (Stage 1)
SERP_API_KEY           # SerpAPI (Stages 1 & 5)
HUNTER_API_KEY         # Hunter.io (Stage 6)
APOLLO_API_KEY         # Apollo.io (Stage 6)
OPENAI_API_KEY         # OpenAI / compatible endpoint for Agents SDK
OPENAI_BASE_URL        # optional; empty = default OpenAI
OPENAI_MODEL           # default: gpt-4o
CORS_ORIGINS           # comma-separated allowed origins
```

## Developer commands
```bash
# Backend (from sugar_india_services/)
uvicorn main:app --reload --host 0.0.0.0 --port 8001

# Frontend (from sugar_india/)
npm run dev

# Celery worker & beat (from sugar_india_services/)
celery -A app.core.celery_app worker --loglevel=info
celery -A app.core.celery_app beat --loglevel=info

# Manual pipeline run (from sugar_india_services/)
python -m app.core.cron                           # all active cities
python -m app.core.cron --city Mumbai             # single city override
python -m app.core.cron --city Mumbai --dry-run   # no real API calls

# Stage-by-stage test runner
python tests/test_pipeline.py --stage 1 --city Gurgaon
python tests/test_pipeline.py --stage all --city Delhi

# Alembic migrations
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

## Frontend: `sugar_india/`
React 18 + Vite + Tailwind CSS + shadcn/ui. Five pages (`Dashboard`, `LeadDiscovery`, `LeadDatabase`, `LeadDetail`, `OutreachCenter`) inside a shared `Layout` with `Sidebar`. All API calls target `http://localhost:8001/api`. shadcn/ui components live in `src/components/ui/`.

## Anti-hallucination rule
If something is not present in the repository, state it is currently unknown. Do not invent architecture, commands, or env var names.
