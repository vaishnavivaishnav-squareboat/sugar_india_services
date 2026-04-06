# Copilot Instructions for `sugar_india_services`

## Actual project layout (flat, no `src/` subdirectory)
All code lives at the repo root — there is **no `src/` tree**:
- `server.py` — FastAPI app (all routes + ORM models duplicated inline + scoring engine)
- `models.py` — canonical SQLAlchemy ORM: `Lead`, `OutreachEmail`, `City`, `PipelineRun`, `Contact`
- `database.py` — async engine, `AsyncSessionLocal`, `Base` (import these; don't redefine)
- `celery_pipeline.py` — Celery app (`horeca_pipeline`), `run_city_pipeline` task, async ETL orchestrator
- `pipeline_stages.py` — 8 async ETL stage functions (≈1 000 lines); import from here for pipeline work
- `genai_helper.py` — `call_genai(prompt, force_json)` with round-robin key rotation over `GENAI_API_KEYS`
- `alembic/` — migration history; add new columns/tables here, never via `create_all` in production
- `tests/test_pipeline.py` — stage-by-stage CLI test runner (see commands below)

## Architecture: two parallel data paths
1. **Manual API path** — `server.py` FastAPI routes; leads created via `POST /api/leads`, scored by `calculate_lead_score()`, stored with `make_lead_obj()`; outreach emails generated on demand via Gemini.
2. **Automated pipeline path** — `celery_pipeline.py` drives a weekly round-robin over `cities` table; calls all 8 stages in `pipeline_stages.py`; Celery wraps async stages with `asyncio.run(_async_pipeline())`.

**Critical**: `server.py` defines its own inline `LeadModel`/`OutreachEmailModel` (using `mapped_column`) separate from `models.py` (using `Column`). The canonical ORM for pipeline and new code is `models.py`. Don't add new tables to `server.py`.

## Key design decisions
- **IDs**: `Lead` uses `uuid4` strings; `City`/`PipelineRun`/`Contact` use integer PKs + a `ulid` surrogate.
- **AI**: `call_genai()` always uses `gemini-2.0-flash`; pass `force_json=True` to get `application/json` MIME type back. Multiple `GENAI_API_KEYS` (comma-separated) are rotated via `itertools.cycle`.
- **Scoring**: `calculate_lead_score()` in `server.py` returns `(score, priority, reasoning)`; priority thresholds: ≥70 = High, ≥40 = Medium, else Low.
- **Celery async bridge**: Celery tasks are sync; async pipeline stages run via `asyncio.run()` inside the task body.
- **SerpAPI**: synchronous `serpapi.Client` is run in a `ThreadPoolExecutor(max_workers=4)` to avoid blocking the event loop.

## Required env vars (see `.env.example`)
```
DATABASE_URL          # asyncpg URL for pipeline; server.py also reads this
GENAI_API_KEYS        # comma-separated Gemini API keys
SERP_API_KEY          # SerpAPI (Stage 1 extraction)
HUNTER_API_KEY        # Hunter.io (Stage 6 email enrichment)
APOLLO_API_KEY        # Apollo.io (Stage 6 email enrichment)
CELERY_BROKER_URL     # redis://localhost:6379/0
CELERY_RESULT_BACKEND # redis://localhost:6379/1
```

## Developer commands
```bash
# Run API server
uvicorn server:app --reload

# Run Celery worker
celery -A celery_pipeline worker --loglevel=info

# Run Celery beat (weekly scheduler)
celery -A celery_pipeline beat --loglevel=info

# Run a single pipeline stage (from repo root)
python tests/test_pipeline.py --stage 1 --city Gurgaon
python tests/test_pipeline.py --stage 2 --city Gurgaon
python tests/test_pipeline.py --stage all --city Delhi
python tests/test_pipeline.py --stage all --city Gurgaon --dry-run  # no real API calls

# Alembic migrations
alembic upgrade head
alembic revision --autogenerate -m "describe change"
```

## Domain & schema conventions
- HoReCa segments in scope: `Restaurant`, `Cafe`, `Hotel`, `Catering`, `Bakery`, `Mithai`, `IceCream`, `CloudKitchen` — but pipeline currently only queries `Restaurant` (others commented out in `HORECA_QUERY_MAP`).
- `Lead.highlights`, `offerings`, `dining_options` are JSON arrays. `sugar_signal_from_highlights` (bool) and `highlight_sugar_signals` (JSON list) are AI-detected fields.
- `PipelineRun.logs` is a JSON dict keyed by stage name (`"stage_1"` … `"stage_8"`), each with `{message, at}`.
- City selection is round-robin by `last_processed_at ASC NULLS FIRST, priority DESC`.

## Anti-hallucination rule
- If something is not present in the repository, state that it is currently unknown.
- Do not invent architecture, commands, or standards.
