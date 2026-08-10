"""Engine, фабрика сессий, создание таблиц."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, echo=False, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_models(engine: AsyncEngine) -> None:
    """Простейшая «миграция»: create_all. Для продакшена — Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
