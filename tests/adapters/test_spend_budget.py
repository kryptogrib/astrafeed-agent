import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.repository.sqlite.spend_budget import SqliteSpendBudget
from astrafeed.domain.spend_budget import BudgetExceeded


@pytest.mark.asyncio
async def test_fresh_schema_has_no_users_fk_and_daily_cap_is_global(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'budget.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)
    budget = SqliteSpendBudget(
        session, daily_limit=1.0, clock=lambda: datetime(2026, 9, 23, tzinfo=UTC)
    )
    try:
        await budget.reserve(0, 0.75)
        with pytest.raises(BudgetExceeded):
            await budget.reserve(1, 0.30)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_reservations_and_settlements_are_serialized(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'parallel-budget.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)
    budget = SqliteSpendBudget(session, daily_limit=5.0)
    try:
        reservations = await asyncio.gather(*(budget.reserve(0, 0.05) for _ in range(32)))
        await asyncio.gather(*(budget.settle(reservation, 0.001) for reservation in reservations))
        assert len(set(reservations)) == 32
    finally:
        await engine.dispose()
