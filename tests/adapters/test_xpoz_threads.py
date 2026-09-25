from datetime import UTC, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.repository.sqlite.xpoz import SqliteXpozThreads
from astrafeed.domain.models import DiscussionComment


@pytest.mark.asyncio
async def test_reply_counts_batch_upsert_preserves_fetched_comments(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'xpoz.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteXpozThreads(async_sessionmaker(engine, expire_on_commit=False))
    comment = DiscussionComment("reply-1", "Reply", datetime(2026, 9, 25, tzinfo=UTC))
    await store.save_comments("post-1", [comment], truncated=False)
    seen: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("INSERT"):
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        await store.record_reply_counts({f"post-{i}": i for i in range(425)})
        assert len(seen) <= 3
        assert await store.reply_counts(["post-1", "post-424"]) == {
            "post-1": 1,
            "post-424": 424,
        }
        assert await store.cached_comments("post-1") == [comment]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
        await engine.dispose()


@pytest.mark.asyncio
async def test_reply_counts_chunks_large_lookup(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'xpoz-lookup.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteXpozThreads(async_sessionmaker(engine))
    counts = {f"post-{i}": i for i in range(1201)}
    await store.record_reply_counts(counts)
    selects: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        assert await store.reply_counts(list(counts)) == counts
        assert len(selects) == 3
        assert all(statement.count("?") <= 500 for statement in selects)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
        await engine.dispose()
