import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.sqlite.agenda import (
    SqliteAgendaStore,
    dumps,
    migrate_agenda_index_tables,
)
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
    IndexedFragment,
    PublicationVersion,
    Snapshot,
    StoryCard,
    StoryLink,
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
        await store.record_publication(
            PublicationVersion(
                "done", 1, "done", "done", text_hash("done"), now, now, "@a", "https://t.me/a/done"
            )
        )
        # Only queued, retryable posts before the cutoff; processed history is not read.
        pending = await store.retryable_publications(now)
        assert [pub.publication_id for pub in pending] == ["new"]
        assert await store.retryable_publications(now - timedelta(hours=3)) == []
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
        statements: list[str] = []

        def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement.lower())

        event.listen(engine.sync_engine, "before_cursor_execute", record_sql)
        try:
            await store.publish_snapshot(
                replace(useful, snapshot_id="snap-20260924T130000Z-p128", agenda=())
            )
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", record_sql)
        snapshot_reads = [
            sql for sql in statements if "from agenda_snapshot" in sql and sql.startswith("select")
        ]
        assert len(snapshot_reads) == 1  # only the immutable-id lookup
        assert sum(sql.startswith("update agenda_snapshot") for sql in statements) == 1
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


@pytest.mark.asyncio
async def test_links_and_fragments_are_read_by_index_after_legacy_json_migration(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'index.db'}")
    t = datetime(2026, 9, 25, tzinfo=UTC)
    old_link = StoryLink("story-1", "pub-old", 1, 0, 0)
    old_fragment = IndexedFragment("pub-old", t - timedelta(days=30), 0, "old", (), "old")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("INSERT INTO agenda_json VALUES ('link', 'pub-old:1:0:0:story-1', :p)"),
            {"p": dumps(old_link)},
        )
        await conn.execute(
            text("INSERT INTO agenda_json VALUES ('fragment', 'pub-old:0', :p)"),
            {"p": dumps(old_fragment)},
        )
        await migrate_agenda_index_tables(conn)
        await migrate_agenda_index_tables(conn)
    store = SqliteAgendaStore(async_sessionmaker(engine, expire_on_commit=False))
    try:
        new_link = StoryLink("story-1", "pub-new", 1, 0, 0)
        await store.save_link(new_link)
        await store.save_link(new_link)
        await store.index_fragment(IndexedFragment("pub-new", t, 0, "new", (), "new"))

        assert await store.links_for_publications({"pub-old"}) == [old_link]
        assert await store.links_for_publications({"pub-new", "missing"}) == [new_link]
        assert await store.links_for_publications(set()) == []
        assert [f.publication_id for f in await store.fragments_since(t - timedelta(days=1))] == [
            "pub-new"
        ]
        assert len(await store.fragments_since(t - timedelta(days=31))) == 2
        async with engine.connect() as conn:
            legacy = await conn.scalar(text("SELECT count(*) FROM agenda_json"))
        assert legacy == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_link_and_fragment_lookups_keep_key_order_across_in_chunks(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'order.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteAgendaStore(async_sessionmaker(engine, expire_on_commit=False))
    t = datetime(2026, 9, 25, tzinfo=UTC)
    try:
        # Inserted newest-first so storage order differs from key order.
        ids = [f"pub-{n:04d}" for n in range(1200)]
        for pub in reversed(ids):
            await store.save_link(StoryLink("story-1", pub, 1, 0, 0))
        await store.index_fragment(IndexedFragment("pub-b", t, 0, "b", (), "b"))
        await store.index_fragment(IndexedFragment("pub-a", t, 0, "a", (), "a"))

        links = await store.links_for_publications(set(ids))
        assert [link.publication_id for link in links] == ids
        assert [f.publication_id for f in await store.fragments_since(t)] == ["pub-a", "pub-b"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_publishing_deletes_unpublished_snapshots_older_than_two_days(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retention.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteAgendaStore(async_sessionmaker(engine, expire_on_commit=False))
    t = datetime(2026, 9, 26, 12, tzinfo=UTC)
    blank = Snapshot(
        snapshot_id="",
        t=t,
        collected_at=t,
        analyzed_at=t,
        published_at=t,
        coverage=CoverageInfo(1, 0, 0, 1, 1, 0, 0, 1),
        queue_depth=0,
        limitations=(),
        agenda=(),
        agenda_mode="new_or_growing",
    )

    def at(when: datetime, suffix: str = "") -> Snapshot:
        return replace(
            blank, t=when, snapshot_id="snap-" + when.strftime("%Y%m%dT%H%M%SZ") + suffix
        )

    try:
        expired = at(t - timedelta(days=2, minutes=5))
        kept = at(t - timedelta(days=2) + timedelta(minutes=5), "-p32")
        for snapshot in (expired, kept, at(t)):
            await store.publish_snapshot(snapshot)

        assert await store.get_snapshot(expired.snapshot_id) is None
        assert await store.get_snapshot(kept.snapshot_id) == kept
        assert (await store.get_snapshot(None)).snapshot_id == at(t).snapshot_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_storage_drops_unused_fts_table_and_indexes_existing_tables(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with legacy.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql("DROP INDEX ix_spend_reservation_day")
        await conn.exec_driver_sql("DROP INDEX ix_source_coverage_source_end")
        await conn.exec_driver_sql(
            "CREATE VIRTUAL TABLE agenda_fts USING fts5(snapshot_id UNINDEXED, body)"
        )
    await legacy.dispose()

    engine, _ = await _storage(Settings(database_url=f"sqlite+aiosqlite:///{path}"))
    try:
        async with engine.connect() as conn:
            names = set(await conn.scalars(text("SELECT name FROM sqlite_master")))
            journal = await conn.scalar(text("PRAGMA journal_mode"))
        assert "agenda_fts" not in names
        assert {"ix_spend_reservation_day", "ix_source_coverage_source_end"} <= names
        assert journal == "wal"
    finally:
        await engine.dispose()
