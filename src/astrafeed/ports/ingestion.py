from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from astrafeed.domain.ingestion import Coverage, Source
from astrafeed.domain.models import Item


class IngestionStore(Protocol):
    """Shared public-source catalog and raw-item cache.

    Not a personal Repository: originals are stored once per
    ``(source_id, external_id)`` and may be read by many user-scoped passes.
    """

    async def upsert_source(self, telegram_id: int) -> Source: ...
    async def upsert_rss_source(self, url: str) -> Source: ...
    async def get_source(self, source_id: int) -> Source | None: ...
    async def store_items(self, source_id: int, items: Sequence[Item]) -> None: ...
    async def read_window(self, source_id: int, start: datetime, end: datetime) -> list[Item]: ...
    async def read_window_page(
        self,
        source_id: int,
        start: datetime,
        end: datetime,
        *,
        after: tuple[datetime, str] | None,
        limit: int,
    ) -> list[Item]: ...
    async def count_window(self, source_id: int, start: datetime, end: datetime) -> int: ...
    async def coverage(self, source_id: int, start: datetime, end: datetime) -> Coverage: ...
    async def mark_coverage(
        self, source_id: int, start: datetime, end: datetime, complete: bool
    ) -> None: ...
    async def get_ingest_watermark(self, source_id: int) -> datetime | None: ...
    async def set_ingest_watermark(self, source_id: int, value: datetime) -> None: ...
