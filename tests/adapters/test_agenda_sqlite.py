import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.sqlite.agenda import SqliteAgendaStore
from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.application.agenda_extract import analyze_publication
from astrafeed.cli import _storage
from astrafeed.config import Settings
from astrafeed.domain.agenda import (
    CLASSIFIER_VERSION,
    Claim,
    CoverageInfo,
    ExtractionResult,
    Fragment,
    PublicationVersion,
    Snapshot,
    StoryCard,
    analysis_reuse_key,
    publication_id,
    text_hash,
)


class OnceExtractor:
    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, text: str) -> ExtractionResult:
        self.calls += 1
        quote = "SEC одобрила спотовый ETH ETF."
        return ExtractionResult(
            reuse_key=analysis_reuse_key(text_hash(text)),
            text_hash=text_hash(text),
            classifier_version=CLASSIFIER_VERSION,
            status="ok",
            fragments=(
                Fragment(
                    text=quote,
                    start=0,
                    end=len(quote),
                    claims=(
                        Claim(
                            kind="event",
                            speaker="author",
                            quote=quote,
                            start=0,
                            end=len(quote),
                        ),
                    ),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_sqlite_expires_stale_queue_work_without_counting_it_as_active(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'queue.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteAgendaStore(async_sessionmaker(engine, expire_on_commit=False))
    now = datetime(2026, 9, 25, 12, tzinfo=UTC)
    try:
        for name, age in (("old", 13), ("new", 2)):
            await store.record_publication(
                PublicationVersion(
                    name,
                    1,
                    name,
                    name,
                    text_hash(name),
                    now - timedelta(hours=age),
                    now,
                    "@a",
                    f"https://t.me/a/{name}",
                )
            )
            await store.enqueue(name, "new")
        await store.expire_before(now - timedelta(hours=12))
        assert set(await store.queued_ids()) == {"old", "new"}
        assert await store.retryable_ids() == ["new"]
        assert await store.queue_depth() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_reuses_extraction_after_reopen(tmp_path):
    path = tmp_path / "agenda.db"
    url = f"sqlite+aiosqlite:///{path}"
    text = "SEC одобрила спотовый ETH ETF. Это событие."
    pub = PublicationVersion(
        publication_id=publication_id(1, "10"),
        source_id=1,
        external_id="10",
        text=text,
        text_hash=text_hash(text),
        published_at=datetime(2026, 9, 23, tzinfo=UTC),
        detected_at=datetime(2026, 9, 23, tzinfo=UTC),
        channel_ref="@alpha",
        link="https://t.me/alpha/10",
    )
    extractor = OnceExtractor()

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)
    store = SqliteAgendaStore(session)
    await store.record_publication(pub)
    first = await analyze_publication(store, extractor, pub)
    assert first.status == "ok"
    await engine.dispose()

    engine = create_async_engine(url)
    session = async_sessionmaker(engine, expire_on_commit=False)
    store = SqliteAgendaStore(session)
    second = await analyze_publication(store, extractor, pub)
    assert second.status == "ok"
    assert extractor.calls == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_accepts_concurrent_embedding_cache_writes(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'parallel.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteAgendaStore(async_sessionmaker(engine, expire_on_commit=False))
    try:
        await asyncio.gather(
            *(store.save_embedding(f"key-{index}", [float(index)]) for index in range(32))
        )
        assert await store.get_embedding("key-31") == [31.0]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_finds_latest_nonempty_snapshot(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'snapshots.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteAgendaStore(async_sessionmaker(engine, expire_on_commit=False))
    t = datetime(2026, 9, 24, tzinfo=UTC)
    useful = Snapshot(
        snapshot_id="snap-20260924T120000Z-p32",
        t=t,
        collected_at=t,
        analyzed_at=t,
        published_at=t,
        coverage=CoverageInfo(1, 0, 0, 1, 1, 0, 0, 1),
        queue_depth=0,
        limitations=(),
        agenda=(
            StoryCard(
                story_id="story-1",
                title="Потоки ETH ETF",
                entities=("Ethereum",),
                current_channels=1,
                previous_channels=0,
                growth=1,
                growth_null_reason=None,
                first_seen=t,
                freshness=t,
                explanation="Потоки ETH ETF",
                claims=(),
            ),
        ),
        agenda_mode="new_or_growing",
    )
    try:
        await store.publish_snapshot(useful)
        assert await store.get_snapshot(None) is useful
        reopened = SqliteAgendaStore(async_sessionmaker(engine, expire_on_commit=False))
        pinned = await reopened.get_snapshot(useful.snapshot_id)
        assert pinned is not None
        await reopened.publish_snapshot(pinned)
        with pytest.raises(ValueError, match="immutable"):
            await store.publish_snapshot(replace(useful, agenda=()))
        assert await store.get_snapshot(useful.snapshot_id) == useful
        await store.publish_snapshot(
            replace(useful, snapshot_id="snap-20260924T130000Z-p128", agenda=())
        )
        assert (await store.get_snapshot(None)).snapshot_id == "snap-20260924T130000Z-p128"
        assert await store.latest_nonempty_snapshot() == useful
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_service_sqlite_storage_uses_wal_and_longer_busy_timeout(tmp_path):
    engine, session = await _storage(
        Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'service.db'}")
    )
    try:
        async with session() as connection:
            assert await connection.scalar(text("PRAGMA journal_mode")) == "wal"
            assert await connection.scalar(text("PRAGMA busy_timeout")) == 30000
    finally:
        await engine.dispose()
