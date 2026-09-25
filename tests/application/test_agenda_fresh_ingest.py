from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.repository.memory import InMemoryRepository
from astrafeed.application.ingestion import IngestionCoordinator
from astrafeed.domain.models import Item
from astrafeed.ports.source import WindowRead

NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


class Reader:
    def __init__(self) -> None:
        self.starts = []

    async def resolve_public_ref(self, ref: str) -> int:
        return 123

    async def read_window(self, telegram_id, start, end, *, max_posts, **kwargs):
        self.starts.append(start)
        items = [
            Item("@news", "old", "Old news", "https://t.me/news/1", NOW - timedelta(hours=13)),
            Item("@news", "new", "New news", "https://t.me/news/2", NOW - timedelta(hours=2)),
        ]
        return WindowRead(tuple(item for item in items if start <= item.timestamp < end), False)


@pytest.mark.asyncio
async def test_new_telegram_source_reads_at_most_12_hours_then_resumes_from_watermark():
    store = InMemoryRepository()
    reader = Reader()
    source = await store.upsert_source(123)
    coordinator = IngestionCoordinator(store, reader, resolver=reader, now=lambda: NOW)

    await coordinator.ensure_window([source.id], NOW - timedelta(hours=72), NOW)
    assert reader.starts == [NOW - timedelta(hours=12)]
    assert [
        item.external_id
        for item in await store.read_window(source.id, NOW - timedelta(hours=72), NOW)
    ] == ["new"]

    await coordinator.ensure_window(
        [source.id], NOW - timedelta(hours=72), NOW + timedelta(hours=1)
    )
    assert reader.starts[-1] >= NOW
