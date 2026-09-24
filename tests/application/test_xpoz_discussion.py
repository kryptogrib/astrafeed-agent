from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.repository.sqlite.xpoz import SqliteXpozThreads
from astrafeed.application.xpoz_discussion import XpozComments
from astrafeed.domain.models import Item


@pytest.mark.asyncio
async def test_xpoz_comments_are_fetched_once_and_reused_after_reader_restart(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'comments.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteXpozThreads(async_sessionmaker(engine, expire_on_commit=False))
    await store.record_reply_counts({"123": 5})

    class Reader:
        def __init__(self):
            self.calls = 0

        async def comments(self, post_id):
            self.calls += 1
            return [
                SimpleNamespace(
                    id="456",
                    text="Important question about ETH",
                    author_username="alice",
                    created_at=datetime(2026, 9, 25, tzinfo=UTC),
                    reply_to_tweet_id=post_id,
                )
            ], False

    reader = Reader()
    item = Item(
        "x/@WuBlockchain",
        "123",
        "post",
        "https://x.com/WuBlockchain/status/123",
        datetime(2026, 9, 25, tzinfo=UTC),
    )
    comments = XpozComments(reader, store)
    assert await comments.reply_counts(item.channel_ref, ["123"]) == {"123": 5}
    first = await comments.fetch_comments(item, limit=40)
    second = await XpozComments(reader, store).fetch_comments(item, limit=40)
    assert first == second
    assert reader.calls == 1
    assert first[0].link == "https://x.com/alice/status/456"
    await engine.dispose()


@pytest.mark.asyncio
async def test_xpoz_comments_are_paced_across_the_day(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'paced.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteXpozThreads(async_sessionmaker(engine, expire_on_commit=False))
    for post_id in ("1", "2", "3"):
        await store.save_comments(post_id, [], False)

    class Reader:
        calls = 0

        async def comments(self, post_id):
            self.calls += 1
            return [], False

    reader = Reader()
    item = Item(
        "x/@WuBlockchain",
        "4",
        "post",
        "https://x.com/WuBlockchain/status/4",
        datetime(2026, 9, 25, tzinfo=UTC),
    )
    assert await XpozComments(reader, store).fetch_comments(item, limit=40) == []
    assert reader.calls == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_paid_comment_attempt_is_cached_and_counted(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'failure.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteXpozThreads(async_sessionmaker(engine, expire_on_commit=False))

    class Reader:
        calls = 0

        async def comments(self, post_id):
            self.calls += 1
            raise TimeoutError("unknown paid outcome")

    reader = Reader()
    item = Item(
        "x/@WuBlockchain",
        "123",
        "post",
        "https://x.com/WuBlockchain/status/123",
        datetime.now(UTC),
    )
    comments = XpozComments(reader, store)
    with pytest.raises(TimeoutError):
        await comments.fetch_comments(item, limit=40)
    assert await comments.fetch_comments(item, limit=40) == []
    assert await store.fetched_count() == 1
    assert reader.calls == 1
    await engine.dispose()
