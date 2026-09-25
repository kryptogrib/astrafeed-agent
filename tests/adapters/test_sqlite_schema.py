import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from astrafeed.adapters.repository.sqlite.agenda import dumps
from astrafeed.adapters.repository.sqlite.schema import LATEST_SCHEMA_VERSION, migrate_schema
from astrafeed.domain.agenda import Entity


@pytest.mark.asyncio
async def test_versioned_schema_migrations_start_empty_and_are_idempotent(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    try:
        await migrate_schema(engine)
        await migrate_schema(engine)
        async with engine.connect() as conn:
            version = await conn.scalar(text("SELECT version FROM schema_version WHERE id = 1"))
            tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
        assert version == LATEST_SCHEMA_VERSION
        assert "agenda_entity_token" in tables
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_versioned_schema_migrations_upgrade_previous_schema(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'previous.db'}")
    async with engine.begin() as conn:
        await conn.exec_driver_sql(
            "CREATE TABLE source (id INTEGER PRIMARY KEY, telegram_id INTEGER NOT NULL UNIQUE)"
        )
        await conn.exec_driver_sql(
            "CREATE TABLE spend_reservation (id VARCHAR PRIMARY KEY, principal_id INTEGER, "
            "day VARCHAR, amount_micros INTEGER, settled BOOLEAN)"
        )
        await conn.exec_driver_sql(
            "CREATE TABLE agenda_json (kind VARCHAR, item_id VARCHAR, payload TEXT, "
            "PRIMARY KEY (kind, item_id))"
        )
        entity = Entity("eth", "Ethereum", aliases=("ETH",))
        await conn.exec_driver_sql(
            "INSERT INTO agenda_json VALUES ('entity', 'eth', :payload)",
            {"payload": dumps(entity)},
        )
    try:
        await migrate_schema(engine)
        async with engine.connect() as conn:
            source_columns = await conn.run_sync(
                lambda sync: {column["name"] for column in inspect(sync).get_columns("source")}
            )
            spend_columns = await conn.run_sync(
                lambda sync: {
                    column["name"] for column in inspect(sync).get_columns("spend_reservation")
                }
            )
            token = await conn.scalar(
                text(
                    "SELECT token FROM agenda_entity_token "
                    "WHERE entity_id='eth' AND token='ethereum'"
                )
            )
        assert "rss_url" in source_columns
        assert {"created_at", "outcome"} <= spend_columns
        assert token == "ethereum"
    finally:
        await engine.dispose()
