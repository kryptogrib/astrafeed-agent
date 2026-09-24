import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.repository.sqlite.spend_budget import (
    SqliteSpendBudget,
    migrate_spend_reservations,
)
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


@pytest.mark.asyncio
async def test_summary_separates_active_timeout_and_old_reservations(tmp_path):
    moment = datetime(2026, 9, 24, 12, tzinfo=UTC)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'summary.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)
    budget = SqliteSpendBudget(session, clock=lambda: moment)
    try:
        active = await budget.reserve(0, 0.5)
        timeout = await budget.reserve(0, 0.5)
        settled = await budget.reserve(0, 0.5)
        await budget.fail(timeout, "timeout")
        await budget.settle(settled, 0.01)
        summary = await budget.summary()
        assert active != timeout
        assert summary["active_count"] == 1
        assert summary["timed_out_count"] == 1
        assert summary["unsettled_usd"] == 1.0
        assert summary["settled_usd"] == 0.01
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_existing_reservations_migrate_as_unknown_without_clearing_charge(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(
                "CREATE TABLE spend_reservation (id VARCHAR PRIMARY KEY, principal_id INTEGER, "
                "day VARCHAR, amount_micros INTEGER, settled BOOLEAN)"
            )
            await conn.exec_driver_sql(
                "INSERT INTO spend_reservation VALUES ('legacy', 0, '2026-09-24', 8450000, 0)"
            )
            await migrate_spend_reservations(conn)
        session = async_sessionmaker(engine, expire_on_commit=False)
        summary = await SqliteSpendBudget(session).summary()
        assert summary["unsettled_usd"] == 8.45
        assert summary["legacy_unknown_count"] == 1
        assert summary["active_count"] == 0
    finally:
        await engine.dispose()
