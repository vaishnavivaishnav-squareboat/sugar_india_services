"""
app/db/session.py
─────────────────────────────────────────────────────────────────────────────
Database engine, session factory, and declarative Base.
All ORM models must inherit from Base defined here.
─────────────────────────────────────────────────────────────────────────────
"""
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import DATABASE_URL

# ── FastAPI engine (shared pool, single persistent event loop) ────────────────
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Celery session factory (NullPool — no cross-loop connection reuse) ─────────
def _make_celery_engine():
    """Fresh engine with NullPool for each asyncio.run() call in Celery tasks."""
    return create_async_engine(DATABASE_URL, echo=False, poolclass=NullPool)


@asynccontextmanager
async def celery_session():
    """
    Async context manager yielding a fresh AsyncSession backed by NullPool.

    Use inside Celery task .run() methods (which call asyncio.run() and spin
    up a new event loop each time).  Avoids the 'Future attached to a
    different loop' RuntimeError that occurs when a pooled asyncpg connection
    created on a previous loop is reused on the new one.

    Usage:
        async with celery_session() as session:
            result = await session.execute(...)
    """
    _engine = _make_celery_engine()
    _factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with _factory() as session:
        try:
            yield session
        finally:
            await session.close()
    await _engine.dispose()


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency: yields an AsyncSession and closes it afterwards."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
