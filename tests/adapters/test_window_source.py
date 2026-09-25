from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.memory import InMemoryRepository
from astrafeed.adapters.repository.sqlite.ingestion import SqliteIngestionStore
from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.source.window import WindowSource
from astrafeed.domain.models import Channel, Item
from astrafeed.domain.progress import processed_item_signature


@pytest.mark.asyncio
async def test_window_source_pages_past_seen_cursor_items_and_caps_sql_reads(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'window.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteIngestionStore(async_sessionmaker(engine, expire_on_commit=False))
    source = await store.upsert_source(42)
    repo = InMemoryRepository()
    channel = Channel("@channel", "Channel", id=1, source_id=source.id)
    now = datetime(2026, 9, 25, tzinfo=UTC)
    items = [Item("original", f"old-{i:03}", "Old", f"https://x/{i}", now) for i in range(300)] + [
        Item("original", f"new-{i}", "New", f"https://x/new/{i}", now + timedelta(seconds=1))
        for i in range(3)
    ]
    await store.store_items(source.id, items)
    await repo.record_seen(
        {processed_item_signature(channel.id, item.external_id) for item in items[:300]}, now
    )
    selects: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT") and "raw_item" in statement:
            selects.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        feed = WindowSource(
            store, repo=repo, max_posts_per_channel=2, start=now, end=now + timedelta(hours=1)
        )
        result = await feed.fetch_new_items(channel, now)
        assert [item.external_id for item in result] == ["new-0", "new-1"]
        assert all(item.channel_ref == "@channel" for item in result)
        assert feed.truncated
        assert len(selects) > 1
        assert all("LIMIT" in statement.upper() for statement in selects)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
        await engine.dispose()
