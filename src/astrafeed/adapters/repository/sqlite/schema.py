"""Versioned, restartable SQLite schema migrations."""

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from astrafeed.adapters.repository.sqlite.agenda import (
    drop_unused_search_index,
    migrate_agenda_entity_tokens,
    migrate_agenda_index_tables,
)
from astrafeed.adapters.repository.sqlite.ingestion import migrate_rss_sources
from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.repository.sqlite.spend_budget import migrate_spend_reservations

LATEST_SCHEMA_VERSION = 6
Migration = Callable[[AsyncConnection], Awaitable[None]]


async def _ensure_indexes(connection: AsyncConnection) -> None:
    def create(sync_connection) -> None:
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(sync_connection, checkfirst=True)

    await connection.run_sync(create)


MIGRATIONS: tuple[Migration, ...] = (
    migrate_rss_sources,
    migrate_spend_reservations,
    migrate_agenda_index_tables,
    drop_unused_search_index,
    migrate_agenda_entity_tokens,
    _ensure_indexes,
)


async def migrate_schema(engine: AsyncEngine) -> None:
    """Create missing tables, then run each outstanding migration transactionally."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)"
        )
        version = await connection.scalar(text("SELECT version FROM schema_version WHERE id = 1"))
        if version is None:
            await connection.exec_driver_sql(
                "INSERT INTO schema_version (id, version) VALUES (1, 0)"
            )
            version = 0

    for next_version, migration in enumerate(MIGRATIONS, start=1):
        if next_version <= int(version):
            continue
        async with engine.begin() as connection:
            await migration(connection)
            await connection.execute(
                text("UPDATE schema_version SET version = :version WHERE id = 1"),
                {"version": next_version},
            )
