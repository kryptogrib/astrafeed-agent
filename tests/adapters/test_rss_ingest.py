from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.memory import InMemoryRepository
from astrafeed.adapters.repository.sqlite.ingestion import (
    SqliteIngestionStore,
    migrate_rss_sources,
)
from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.source.rss import RssReader, parse_feed
from astrafeed.application.rss_ingest import collect_feeds, resolve_feeds
from astrafeed.domain.models import Item

START = datetime(2026, 9, 25, tzinfo=UTC)
URL = "https://example.com/feed"


@pytest.mark.asyncio
async def test_new_rss_source_stores_only_the_last_12_hours():
    store = InMemoryRepository()
    feeds = await resolve_feeds(store, [URL])
    (source_id,) = feeds
    end = START + timedelta(days=1)

    class Reader:
        async def read(self, url):
            return [
                Item("news", "old", "Old", "https://example.com/old", end - timedelta(hours=13)),
                Item("news", "new", "New", "https://example.com/new", end - timedelta(hours=1)),
            ]

    await collect_feeds(store, Reader(), feeds, end - timedelta(hours=72), end)
    items = await store.read_window(source_id, end - timedelta(hours=72), end)
    assert [item.external_id for item in items] == ["new"]
    assert await store.get_ingest_watermark(source_id) == end


def test_parse_rss_and_atom_preserve_original_link_and_date():
    rss = b"""<rss version="2.0"><channel><title>Publisher</title>
    <item><guid>story-1</guid><title>Bitcoin rises</title>
    <description><![CDATA[<p>Market update</p>]]></description>
    <link>https://example.com/story</link>
    <pubDate>Fri, 25 Sep 2026 00:00:00 GMT</pubDate></item></channel></rss>"""
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Publisher</title>
    <entry><id>story-1</id><title>Bitcoin rises</title>
    <summary>Market update</summary><link href="https://example.com/story"/>
    <published>2026-09-25T00:00:00Z</published></entry></feed>"""
    for body in (rss, atom):
        (item,) = parse_feed(body, URL)
        assert item.link == "https://example.com/story"
        assert item.timestamp == START
        assert item.channel_name == "Publisher"
        assert "Market update" in item.text


@pytest.mark.asyncio
async def test_rss_collection_is_idempotent_and_incomplete_history_is_visible(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rss.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await migrate_rss_sources(connection)
    store = SqliteIngestionStore(async_sessionmaker(engine, expire_on_commit=False))
    feeds = await resolve_feeds(store, [URL, URL])
    (source_id,) = feeds
    body = b"""<rss><channel><title>Publisher</title>
    <item><guid>one</guid><title>News</title><link>https://example.com/one</link>
    <pubDate>Fri, 25 Sep 2026 12:00:00 GMT</pubDate></item></channel></rss>"""
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    client = httpx.AsyncClient(transport=transport)
    async with client:
        reader = RssReader(client)
        for _ in range(2):
            await collect_feeds(store, reader, feeds, START, START + timedelta(days=1))
    assert len(await store.read_window(source_id, START, START + timedelta(days=1))) == 1
    assert not (await store.coverage(source_id, START, START + timedelta(days=1))).complete
    assert (await store.get_source(source_id)).telegram_id is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_migration_adds_feed_identity_to_existing_source_table(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            "CREATE TABLE source (id INTEGER PRIMARY KEY, telegram_id INTEGER NOT NULL UNIQUE)"
        )
        await migrate_rss_sources(connection)
    store = SqliteIngestionStore(async_sessionmaker(engine, expire_on_commit=False))
    rss = await store.upsert_rss_source(URL)
    assert rss == await store.upsert_rss_source(URL)
    assert rss.rss_url == URL
    telegram = await store.upsert_source(12345)
    assert telegram.telegram_id == 12345
    await engine.dispose()
