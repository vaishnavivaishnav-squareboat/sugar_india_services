"""
main.py
─────────────────────────────────────────────────────────────────────────────
FastAPI application entry point for the Dhampur Green HORECA Lead Intelligence API.

Run the server:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
─────────────────────────────────────────────────────────────────────────────
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

# Import config values from app.core.config
from app.core.config import CORS_ORIGINS

# Import DB engine and Base (must happen after load_dotenv so DATABASE_URL is set)
from app.db.session import engine, Base

# Import all ORM models so they register with Base.metadata before create_all
from app.db.orm import Lead, OutreachEmail, City, PipelineRun, Segment, Contact  # noqa: F401

# Import the API router
from app.api import api_router


# ─── LIFESPAN ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create all tables on startup; dispose the engine on shutdown."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


# ─── APP ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Dhampur Green HORECA Lead Intelligence API",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)

_origins = CORS_ORIGINS.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}
