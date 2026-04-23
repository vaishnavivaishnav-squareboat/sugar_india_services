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
| `app/agents/` | OpenAI Agents SDK: `classify_agent.py` (Stage 2), `contact_agent.py` (Stage 5), `email_agent.py` (Stage 7), `bridge.py` (entry point for stages 2/5/7), `orchestrator.py` (multi-agent flow) |
| `app/core/openai_client.py` | `call_openai(prompt, force_json)` — async OpenAI chat completions helper used by all pipeline stages and API endpoints |
| `app/utils/scoring.py` | `calculate_lead_score(data)` → `(score, priority, reasoning)`; `make_lead_obj()` |
| `app/utils/domain_utils.py` | `extract_domain(url)` — normalises website URLs to bare domain |
| `app/utils/email_patterns.py` | `patterns_as_contacts(name, domain)` — last-resort pattern-generated email contacts |
| `app/utils/smtp.py` | SMTP helper for direct email delivery (used outside the pipeline) |
| `app/utils/agent_flow.py` | Utilities for OpenAI Agents SDK flow orchestration |
| `app/providers/` | Thin provider wrappers: `hunter_provider.py`, `apollo_provider.py`, `snov_provider.py`, `serpapi_provider.py` — import as `from app.providers import hunter_provider` |
| `app/services/` | Domain service layer organised by pipeline stage: `classification/`, `deduplication/`, `email_generation/`, `enrichment/` (contact + email), `extraction/`, `filtering/`, `storage/` |
| `app/core/celery_app.py` | Celery app `horeca_pipeline`; **one city per invocation** (round-robin by `last_processed_at ASC`) |
| `app/core/cron.py` | Weekly cron script; **all active cities per run**; uses `fcntl` lock to prevent overlap |
| `app/prompts/` | Prompt builder functions (business_intelligence, contact_extraction, email_generation, lead_qualify, lead_email_api) |
| `app/schemas/` | Pydantic request/response models |

### Two parallel automation paths
1. **Celery path** (`app/core/celery_app.py`) — Celery beat triggers `run_city_pipeline` weekly; selects ONE city round-robin; bridges sync→async via `asyncio.run()`.
2. **Cron path** (`app/core/cron.py`) — direct Python script; processes ALL active cities; run manually or via `crontab`.

### 8-stage ETL pipeline (`app/pipelines/stages.py`)
1. `extract_business_data` — SerpAPI Google Maps; runs in `ThreadPoolExecutor(max_workers=4)` to avoid blocking the async loop
2. `ai_process_business_data` — OpenAI Agents SDK classifies menus, sugar signals, estimates monthly kg
3. `apply_kpi_filtering` — composite score threshold rejection
4. `deduplicate_leads` — fuzzy name + geo dedup + DB cross-check
5. `enrich_contacts` — SerpAPI + OpenAI Agents SDK contact discovery
6. `enrich_emails` — Hunter.io + Apollo.io email lookup
7. `generate_personalized_emails` — OpenAI Agents SDK outreach email generation
8. `store_leads_and_emails` — persist to DB

`HORECA_QUERY_MAP` in `app/core/constants.py` controls which segments run — all 10 segment keys are present (`Bakery`, `IceCream`, `Beverage`, `Restaurant`, `Cafe`, `Hotel`, `Catering`, `CloudKitchen`, `Mithai`, `FoodProcessing`, `Organic`, `Brewery`); only Bakery's optional sub-queries (`cake shop`, `patisserie`) are commented out within the list. `_FULL_QUERY_MAP` is the exhaustive reference version.

### Stage 6 email enrichment
`app/services/enrichment/email_service.py` uses a **5-source fallback chain** (in priority order):
1. Hunter.io `domain_search` → `email_finder`
2. Apollo.io `people_match`
3. Snov.io `domain_search` → `email_finder`
4. Pattern generation (`app/utils/email_patterns.py`)

Each provider is a thin async wrapper in `app/services/providers/`. Domain extraction is centralised in `app/utils/domain_utils.py`.

### AI layer
- **OpenAI** (`app/core/openai_client.py`) — all pipeline stages and API endpoints; `call_openai(prompt, force_json=True)` for JSON responses, `call_openai(prompt)` for plain text; model controlled by `OPENAI_MODEL` env var (default `gpt-4o`)
- **OpenAI Agents SDK** (`app/agents/`) — three self-contained agents (`classify_agent`, `contact_agent`, `email_agent`), each with its own `@function_tool`-typed schema; all accessed via `bridge.py`; **`app/agents/bridge.py` must be imported/run before any agent module** to register the async client and disable tracing
- **Agent import order is critical**: `bridge.py` imports all three agent modules at the top; individual services must import from `bridge.py` (`run_stage2`, `run_stage5`, `run_stage7`), not directly from agent files

### Key conventions
- `Lead.id` = `uuid4` string; `City`, `PipelineRun`, `Contact` use integer PK + ULID surrogate
- Scoring thresholds: `ai_score` ≥ 70 → `High`, ≥ 40 → `Medium`, else `Low`
- Routes use `async with AsyncSessionLocal() as session:` directly — not the `get_db()` FastAPI dependency
- Celery tasks use `async with celery_session() as session:` (NullPool, defined in `app/db/session.py`) — avoids "Future attached to a different loop" errors from reusing pooled connections across `asyncio.run()` calls
- `model_to_dict()` in `app/utils/__init__.py` serializes any ORM model to dict (ISO-formats datetimes)
- New ORM models → `app/db/orm.py` + Alembic migration; never use `create_all` in production
- `Lead.highlights`, `offerings`, `dining_options`, `highlight_sugar_signals` are `JSON` columns (arrays)
- `PipelineRun.logs` uses `MySQLJSON` from `sqlalchemy.dialects.mysql` — imported directly in `orm.py`; this is a legacy artifact from an earlier MySQL target and does not affect PostgreSQL deployments

## Frontend: `sugar_india/`

React + Vite + Tailwind + shadcn/ui SPA. Five pages wired in `src/App.jsx`:

| Route | Page | Purpose |
|---|---|---|
| `/` | `Dashboard.jsx` | KPI stats + seed-mock-data trigger |
| `/discover` | `LeadDiscovery.jsx` | Trigger pipeline runs per city |
| `/leads` | `LeadDatabase.jsx` | Paginated lead list with filters |
| `/leads/:id` | `LeadDetail.jsx` | Lead detail, AI qualify, email generation |
| `/outreach` | `OutreachCenter.jsx` | Bulk send / follow-up with task polling |

- `vite.config.js` registers a custom `treat-js-files-as-jsx` plugin (esbuild loader) so all `src/**/*.js` files are treated as JSX — do **not** rename components to `.jsx` as a fix for JSX syntax errors
- All pages use **axios** and resolve the backend via `const API = \`${import.meta.env.VITE_BACKEND_URL}/api\``
- Long-running backend tasks (bulk-send, follow-up) return a `task_id`; pages poll `GET /api/outreach/…/{task_id}` until status is terminal
- UI components live in `src/components/ui/` (shadcn/ui primitives) and `src/components/` (app-level: `Layout`, `Sidebar`, `CitiesPanel`, `SegmentsPanel`, `CityCombobox`)

## Required env vars

### Backend (`sugar_india_services/.env`)
```
DATABASE_URL           # asyncpg PostgreSQL URL
GOOGLE_PLACES_API_KEY  # Google Places (Stage 1)
SERP_API_KEY           # SerpAPI (Stages 1 & 5)
HUNTER_API_KEY         # Hunter.io (Stage 6)
APOLLO_API_KEY         # Apollo.io (Stage 6)
SNOV_CLIENT_ID         # Snov.io (Stage 6 tertiary fallback)
SNOV_CLIENT_SECRET     # Snov.io (Stage 6 tertiary fallback)
OPENAI_API_KEY         # OpenAI / compatible endpoint for Agents SDK
OPENAI_BASE_URL        # optional; empty = default OpenAI
OPENAI_MODEL           # default: gpt-4o
CORS_ORIGINS           # comma-separated allowed origins
```

### Frontend (`sugar_india/.env`)
```
VITE_BACKEND_URL       # e.g. http://localhost:8001
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
