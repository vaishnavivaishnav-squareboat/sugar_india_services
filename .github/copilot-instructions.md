# Copilot Instructions — Dhampur Green HORECA Lead Intelligence

## Monorepo layout
Two sibling packages at the repo root:
- `sugar_india_services/` — FastAPI + Celery + OpenAI Agents SDK backend (Python 3.11+, asyncpg/PostgreSQL)
- `sugar_india/` — React 18 + Vite + Tailwind + shadcn/ui frontend

---

## Backend: `sugar_india_services/`

### Key file map
| Path | Purpose |
|---|---|
| `main.py` | FastAPI entry point; registers `api_router`; `Base.metadata.create_all` on lifespan startup |
| `app/db/orm.py` | All ORM models: `Lead`, `OutreachEmail`, `City`, `PipelineRun`, `Segment`, `Contact` |
| `app/db/session.py` | `engine`, `AsyncSessionLocal`, `Base`, `get_db()`, `celery_session()` — import, never redefine |
| `app/core/config.py` | All env vars loaded from `.env`; import typed constants from here only |
| `app/api/` | One router per entity (`lead.py`, `city.py`, `segment.py`, `contact.py`, `outreach.py`, `dashboard.py`); aggregated in `app/api/__init__.py` as `api_router` with `/api` prefix |
| `app/pipelines/stages.py` | **Thin** 8-stage facade — each function is a one-liner delegate to the matching service in `app/services/` |
| `app/agents/` | OpenAI Agents SDK: `classify_agent.py` (Stage 2), `contact_agent.py` (Stage 5), `email_agent.py` (Stage 7), `bridge.py` (single entry point), `orchestrator.py` |
| `app/core/openai_client.py` | `call_openai(prompt, force_json)` — async chat completions helper; all stages and endpoints use this |
| `app/utils/scoring.py` | `calculate_lead_score(data)` → `(score, priority, reasoning)`; `make_lead_obj()` |
| `app/utils/domain_utils.py` | `extract_domain(url)` — normalises website URLs to bare domain |
| `app/utils/email_patterns.py` | `patterns_as_contacts(name, domain)` — last-resort pattern-generated email contacts |
| `app/utils/smtp.py` | SMTP helper for direct email delivery (outside the pipeline) |
| `app/utils/agent_flow.py` | Utilities for OpenAI Agents SDK flow orchestration |
| `app/prompts/` | Prompt builder functions: `business_intelligence`, `contact_extraction`, `email_generation`, `lead_qualify`, `lead_email_api` |
| `app/providers/` | Thin async wrappers: `hunter_provider.py`, `apollo_provider.py`, `snov_provider.py`, `serpapi_provider.py` |
| `app/services/` | Domain service layer by stage: `classification/`, `deduplication/`, `email_generation/`, `enrichment/` (contact + email), `extraction/`, `filtering/`, `storage/` |
| `app/core/celery_app.py` | Celery app `horeca_pipeline`; ONE city per invocation (round-robin by `last_processed_at ASC`) |
| `app/core/cron.py` | Weekly cron script; ALL active cities per run; `fcntl` lock prevents overlap |
| `app/schemas/` | Pydantic request/response models per entity |

### 8-stage ETL pipeline (`app/pipelines/stages.py` → `app/services/`)
1. **`extract_business_data`** → `app/services/extraction/extraction_service.py` — SerpAPI Google Maps + Hunter Discover; `ThreadPoolExecutor(max_workers=4)` for sync SDK calls
2. **`ai_process_business_data`** → `app/services/classification/classification_service.py` — OpenAI Agents SDK: menu classification, sugar signals, monthly kg estimate
3. **`apply_kpi_filtering`** → `app/services/filtering/kpi_service.py` — composite score threshold rejection
4. **`deduplicate_leads`** → `app/services/deduplication/dedup_service.py` — Jaccard name similarity + geo proximity + DB cross-check
5. **`enrich_contacts`** → `app/services/enrichment/contact_service.py` — SerpAPI + OpenAI Agents SDK contact discovery
6. **`enrich_emails`** → `app/services/enrichment/email_service.py` — **5-source fallback**: Hunter.io `domain_search`/`email_finder` → Apollo.io `people_match` → Snov.io `domain_search`/`email_finder` → pattern generation
7. **`generate_personalized_emails`** → `app/services/email_generation/email_gen_service.py` — OpenAI Agents SDK outreach email generation
8. **`store_leads_and_emails`** → `app/services/storage/storage_service.py` — persist to DB

Segment queries are driven by `HORECA_QUERY_MAP` in `app/core/constants.py` (12 active segment keys: `Bakery`, `IceCream`, `Beverage`, `Restaurant`, `Cafe`, `Hotel`, `Catering`, `CloudKitchen`, `Mithai`, `FoodProcessing`, `Organic`, `Brewery`).

### Two automation paths
- **Celery path** (`app/core/celery_app.py`) — beat triggers `run_city_pipeline` weekly; one city; bridges sync→async via `asyncio.run()`
- **Cron path** (`app/core/cron.py`) — run directly; all active cities; safe for `crontab`

### AI / Agents critical rules
- **Import order**: `app/agents/bridge.py` must be the first agents import — it registers the async OpenAI client and disables tracing before other agent modules load. Always import via `from app.agents.bridge import run_stage2, run_stage5, run_stage7`, never directly from agent files.
- `call_openai(prompt, force_json=True)` for structured JSON; `call_openai(prompt)` for plain text. Model controlled by `OPENAI_MODEL` env var (default `gpt-4o`).

### Key conventions
- `Lead.id` = `uuid4` string; `City`, `PipelineRun`, `Contact` use integer PK + ULID surrogate
- Scoring: `ai_score` ≥ 70 → `High`, ≥ 40 → `Medium`, else `Low`
- API routes use `async with AsyncSessionLocal() as session:` directly (not `get_db()` dependency)
- Celery tasks use `async with celery_session() as session:` (NullPool, defined in `app/db/session.py`) — avoids "Future attached to different loop" errors across `asyncio.run()` calls
- `model_to_dict()` in `app/utils/__init__.py` serializes ORM models (ISO-formats datetimes)
- `Lead.highlights`, `offerings`, `dining_options`, `highlight_sugar_signals` are `JSON` columns (arrays)
- `PipelineRun.logs` uses `MySQLJSON` from `sqlalchemy.dialects.mysql` — legacy artifact; does not affect PostgreSQL deployments
- New ORM model → add to `app/db/orm.py` + `alembic revision --autogenerate`; never rely on `create_all` in production

---

## Frontend: `sugar_india/`

React 18 + Vite + Tailwind + shadcn/ui SPA. Five routes in `src/App.jsx`:

| Route | Page | Purpose |
|---|---|---|
| `/` | `Dashboard.jsx` | KPI stats (7 async DB queries via `/api/dashboard/stats`) |
| `/discover` | `LeadDiscovery.jsx` | Trigger pipeline runs per city/segment |
| `/leads` | `LeadDatabase.jsx` | Paginated lead list with filters (city, segment, priority, status, score) |
| `/leads/:id` | `LeadDetail.jsx` | Lead detail, AI qualify (`/qualify-ai`), email generation |
| `/outreach` | `OutreachCenter.jsx` | Bulk send / follow-up with task polling |

- `vite.config.js` registers a custom `treat-js-files-as-jsx` esbuild loader — all `src/**/*.js` files are valid JSX; do **not** rename to `.jsx` to fix JSX syntax errors
- All API calls via axios: `const API = \`${import.meta.env.VITE_BACKEND_URL}/api\``
- Long-running tasks (bulk-send, follow-up) return `task_id`; pages poll `GET /api/outreach/…/{task_id}` until terminal status
- shadcn/ui primitives in `src/components/ui/`; app-level components: `Layout`, `Sidebar`, `CitiesPanel`, `SegmentsPanel`, `CityCombobox`

---

## Required env vars

**Backend** (`sugar_india_services/.env`):
```
DATABASE_URL           # asyncpg PostgreSQL URL (postgresql+asyncpg://...)
SERP_API_KEY           # SerpAPI — Stages 1 & 5
HUNTER_API_KEY         # Hunter.io — Stage 6 primary
APOLLO_API_KEY         # Apollo.io — Stage 6 secondary
SNOV_CLIENT_ID         # Snov.io — Stage 6 tertiary
SNOV_CLIENT_SECRET
OPENAI_API_KEY
OPENAI_BASE_URL        # optional; empty = default OpenAI
OPENAI_MODEL           # default: gpt-4o
CORS_ORIGINS           # comma-separated allowed origins
```

**Frontend** (`sugar_india/.env`):
```
VITE_BACKEND_URL=http://localhost:8001
```

---

## Developer commands

```bash
# Backend (from sugar_india_services/)
uvicorn main:app --reload --host 0.0.0.0 --port 8001

# Frontend (from sugar_india/)
npm run dev

# Celery worker + beat (from sugar_india_services/)
celery -A app.core.celery_app worker --loglevel=info
celery -A app.core.celery_app beat --loglevel=info

# Manual pipeline runs (from sugar_india_services/)
python -m app.core.cron                            # all active cities
python -m app.core.cron --city Mumbai              # single city
python -m app.core.cron --city Mumbai --dry-run    # no real API calls

# Test pipeline by stage (from sugar_india_services/)
python tests/test_pipeline.py --stage 1 --city Gurgaon
python tests/test_pipeline.py --stage all --city Delhi
python tests/test_pipeline.py --mode per-business --city Gurgaon  # run stages 2-8 per-business
python tests/test_pipeline.py --stage all --city Delhi --dry-run  # mock data, no API calls

# Alembic migrations (from sugar_india_services/)
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

---

## Anti-hallucination rule
If something is not verifiable in the repository, say it is currently unknown. Do not invent architecture, commands, env var names, or file paths.
