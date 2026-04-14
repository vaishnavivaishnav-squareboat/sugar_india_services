"""
app/db/session.py
─────────────────────────────────────────────────────────────────────────────
Database engine, session factory, and declarative Base.
All ORM models must inherit from Base defined here.
─────────────────────────────────────────────────────────────────────────────
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency: yields an AsyncSession and closes it afterwards."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
