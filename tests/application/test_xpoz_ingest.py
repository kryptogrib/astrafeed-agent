from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from astrafeed.adapters.repository.memory import InMemoryRepository
from astrafeed.application.xpoz_ingest import (
    collect_xpoz_accounts,
    collect_xpoz_search,
    resolve_xpoz_accounts,
    resolve_xpoz_search,
)

NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


class Reader:
    def __init__(self):
        self.calls = []

    async def posts_by_author(self, handle, start):
        self.calls.append(handle)
        return [
            SimpleNamespace(
                id=f"{handle}-1",
                text=f"News from {handle}",
                author_username=handle,
                created_at=NOW - timedelta(minutes=10),
                is_retweet=False,
                reply_to_tweet_id=None,
                reply_count=3,
            )
        ], False


@pytest.mark.asyncio
async def test_new_xpoz_account_searches_at_most_12_hours():
    store = InMemoryRepository()
    accounts = await resolve_xpoz_accounts(store, ["@WuBlockchain"])

    class RecordingReader(Reader):
        async def posts_by_author(self, handle, start):
            assert start == NOW - timedelta(hours=12)
            return await super().posts_by_author(handle, start)

    await collect_xpoz_accounts(store, RecordingReader(), accounts, NOW - timedelta(hours=48), NOW)
    assert await store.get_ingest_watermark(next(iter(accounts))) == NOW


@pytest.mark.asyncio
async def test_xpoz_schedule_skips_duplicate_rss_publishers_and_unchanged_accounts():
    store = InMemoryRepository()
    accounts = await resolve_xpoz_accounts(
        store, ["@WuBlockchain", "@zachxbt", "@Cointelegraph", "@TheBlock__"]
    )
    reader = Reader()
    assert len(accounts) == 2
    await collect_xpoz_accounts(store, reader, accounts, NOW - timedelta(hours=48), NOW)
    assert reader.calls == ["WuBlockchain", "zachxbt"]
    await collect_xpoz_accounts(
        store, reader, accounts, NOW - timedelta(hours=48), NOW + timedelta(minutes=5)
    )
    assert reader.calls == ["WuBlockchain", "zachxbt"]
    await collect_xpoz_accounts(
        store, reader, accounts, NOW - timedelta(hours=48), NOW + timedelta(hours=6)
    )
    assert reader.calls == ["WuBlockchain", "zachxbt"]
    await collect_xpoz_accounts(
        store, reader, accounts, NOW - timedelta(hours=48), NOW + timedelta(hours=12)
    )
    assert reader.calls == ["WuBlockchain", "zachxbt", "WuBlockchain", "zachxbt"]
    found = [await store.read_window(sid, NOW - timedelta(hours=1), NOW) for sid in accounts]
    assert sum(map(len, found)) == 2
    assert all(items[0].link.startswith("https://x.com/") for items in found)


@pytest.mark.asyncio
async def test_xpoz_failed_fetch_does_not_advance_schedule():
    store = InMemoryRepository()
    accounts = await resolve_xpoz_accounts(store, ["@WuBlockchain"])

    class Failing:
        async def posts_by_author(self, handle, start):
            raise RuntimeError("Xpoz unavailable")

    errors = await collect_xpoz_accounts(store, Failing(), accounts, NOW - timedelta(hours=48), NOW)
    assert errors
    assert await store.get_ingest_watermark(next(iter(accounts))) is None


@pytest.mark.asyncio
async def test_xpoz_collection_records_reply_counts_for_discussion_selection():
    store = InMemoryRepository()
    accounts = await resolve_xpoz_accounts(store, ["@WuBlockchain"])

    class Threads:
        counts = None

        async def record_reply_counts(self, counts):
            self.counts = counts

    threads = Threads()
    await collect_xpoz_accounts(
        store, Reader(), accounts, NOW - timedelta(hours=48), NOW, threads=threads
    )
    assert threads.counts == {"WuBlockchain-1": 3}


@pytest.mark.asyncio
async def test_xpoz_search_reuses_tracked_account_source_and_polls_every_15_minutes():
    store = InMemoryRepository()
    accounts = await resolve_xpoz_accounts(store, ["@WuBlockchain"])
    search_id = await resolve_xpoz_search(store)

    class SearchReader:
        calls = 0

        async def search_crypto(self, start):
            self.calls += 1
            return [
                SimpleNamespace(
                    id="1",
                    text="Bitcoin news",
                    author_username="WuBlockchain",
                    created_at=NOW - timedelta(minutes=1),
                    is_retweet=False,
                    reply_to_tweet_id=None,
                    reply_count=2,
                ),
                SimpleNamespace(
                    id="2",
                    text="Ethereum news",
                    author_username="newvoice",
                    created_at=NOW - timedelta(minutes=2),
                    is_retweet=False,
                    reply_to_tweet_id=None,
                    reply_count=4,
                ),
            ], False

    reader = SearchReader()
    await collect_xpoz_search(store, reader, search_id, accounts, NOW - timedelta(hours=48), NOW)
    await collect_xpoz_search(
        store, reader, search_id, accounts, NOW - timedelta(hours=48), NOW + timedelta(minutes=5)
    )
    assert reader.calls == 1
    await collect_xpoz_search(
        store, reader, search_id, accounts, NOW - timedelta(hours=48), NOW + timedelta(minutes=15)
    )
    assert reader.calls == 2
    tracked_id = next(iter(accounts))
    tracked = await store.read_window(tracked_id, NOW - timedelta(hours=1), NOW)
    general = await store.read_window(search_id, NOW - timedelta(hours=1), NOW)
    assert [item.external_id for item in tracked] == ["1"]
    assert [item.external_id for item in general] == ["2"]


@pytest.mark.asyncio
async def test_xpoz_search_keeps_two_hour_overlap_for_late_indexing():
    store = InMemoryRepository()
    search_id = await resolve_xpoz_search(store)
    await store.set_ingest_watermark(search_id, NOW - timedelta(minutes=15))

    class LateReader:
        starts = []

        async def search_crypto(self, start):
            self.starts.append(start)
            return [
                SimpleNamespace(
                    id="late",
                    text="Breaking Bitcoin news",
                    author_username="newvoice",
                    created_at=NOW - timedelta(minutes=90),
                    is_retweet=False,
                    reply_to_tweet_id=None,
                    reply_count=0,
                )
            ], False

    reader = LateReader()
    await collect_xpoz_search(store, reader, search_id, {}, NOW - timedelta(hours=48), NOW)
    assert reader.starts == [NOW - timedelta(hours=2, minutes=15)]
    assert [
        i.external_id for i in await store.read_window(search_id, NOW - timedelta(hours=2), NOW)
    ] == ["late"]
