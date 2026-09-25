from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.repository.memory import InMemoryRepository
from astrafeed.application.reddit_ingest import collect_reddit_feeds, resolve_reddit_feeds
from astrafeed.domain.models import Item

NOW = datetime(2026, 9, 25, tzinfo=UTC)
FEEDS = [
    "https://www.reddit.com/r/CryptoCurrency/.rss",
    "https://www.reddit.com/r/Bitcoin/.rss",
]


class StubReader:
    def __init__(self, items):
        self.items = items
        self.urls = []

    async def read(self, url):
        self.urls.append(url)
        return self.items


@pytest.mark.asyncio
async def test_combined_reddit_feed_keeps_subreddits_as_distinct_sources():
    store = InMemoryRepository()
    feeds = await resolve_reddit_feeds(store, FEEDS)
    reader = StubReader(
        [
            Item(
                "reddit.com",
                "old",
                "Old",
                "https://www.reddit.com/r/Bitcoin/comments/old",
                NOW - timedelta(days=3),
            ),
            Item(
                "reddit.com",
                "one",
                "Bitcoin news",
                "https://www.reddit.com/r/Bitcoin/comments/one",
                NOW,
            ),
            Item(
                "reddit.com",
                "two",
                "Crypto news",
                "https://www.reddit.com/r/CryptoCurrency/comments/two",
                NOW,
            ),
        ]
    )
    errors = await collect_reddit_feeds(store, reader, feeds, NOW - timedelta(days=2), NOW)
    assert not errors
    assert reader.urls == ["https://www.reddit.com/r/CryptoCurrency+Bitcoin/new/.rss?limit=100"]
    found = {
        (await store.get_source(sid)).rss_url: await store.read_window(
            sid, NOW - timedelta(days=2), NOW
        )
        for sid in feeds
    }
    assert [item.channel_ref for item in found[FEEDS[0]]] == ["r/CryptoCurrency"]
    assert [item.channel_ref for item in found[FEEDS[1]]] == ["r/Bitcoin"]
    for sid in feeds:
        assert not (await store.coverage(sid, NOW - timedelta(days=2), NOW)).complete


@pytest.mark.asyncio
async def test_new_reddit_sources_store_only_the_last_12_hours():
    store = InMemoryRepository()
    feeds = await resolve_reddit_feeds(store, FEEDS)
    reader = StubReader(
        [
            Item(
                "reddit.com",
                "old",
                "Old",
                "https://www.reddit.com/r/Bitcoin/comments/old",
                NOW - timedelta(hours=13),
            ),
            Item(
                "reddit.com",
                "new",
                "New",
                "https://www.reddit.com/r/Bitcoin/comments/new",
                NOW - timedelta(hours=1),
            ),
        ]
    )
    await collect_reddit_feeds(store, reader, feeds, NOW - timedelta(hours=72), NOW)
    bitcoin_id = next(sid for sid, name in feeds.items() if name == "Bitcoin")
    items = await store.read_window(bitcoin_id, NOW - timedelta(hours=72), NOW)
    assert [item.external_id for item in items] == ["new"]
    assert await store.get_ingest_watermark(bitcoin_id) == NOW


@pytest.mark.asyncio
async def test_reddit_rate_limit_leaves_all_subreddit_coverage_incomplete():
    store = InMemoryRepository()
    feeds = await resolve_reddit_feeds(store, FEEDS)

    class RateLimited:
        async def read(self, url):
            raise RuntimeError("429 Too Many Requests")

    errors = await collect_reddit_feeds(store, RateLimited(), feeds, NOW - timedelta(days=2), NOW)
    assert len(errors) == 2
    assert all("429" in reason for reason in errors.values())
    for sid in feeds:
        assert not (await store.coverage(sid, NOW - timedelta(days=2), NOW)).complete
