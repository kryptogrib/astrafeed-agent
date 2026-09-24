from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.sqlite.agenda import SqliteAgendaStore
from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.application.agenda_extract import analyze_publication
from astrafeed.domain.agenda import (
    CLASSIFIER_VERSION,
    Claim,
    ExtractionResult,
    Fragment,
    PublicationVersion,
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
