"""Small in-memory report repository and ingestion cache used by one brief request."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from astrafeed.domain import Channel, CostEntry, Interest, Item, Verdict
from astrafeed.domain.ingestion import Coverage, Source, coverage_for_window
from astrafeed.ports.repository import Repository


class InMemoryRepository(Repository):
    def __init__(self) -> None:
        self._channels: dict[int, Channel] = {}
        self._interests: list[Interest] = []
        self._watermarks: dict[int, datetime] = {}
        self._queue: dict[int, Verdict] = {}
        self._seen: dict[str, datetime] = {}
        self._costs: list[CostEntry] = []
        self._next_channel = 1
        self._next_queue = 1
        self._sources: dict[int, Source] = {}
        self._source_ids: dict[int, int] = {}
        self._rss_source_ids: dict[str, int] = {}
        self._items: dict[tuple[int, str], Item] = {}
        self._coverage: dict[int, list[Coverage]] = {}
        self._ingest_watermarks: dict[int, datetime] = {}

    async def add_channel(self, channel: Channel) -> Channel:
        saved = Channel(**{**channel.__dict__, "id": self._next_channel})
        self._channels[self._next_channel] = saved
        self._next_channel += 1
        return saved

    async def list_channels(self) -> list[Channel]:
        return list(self._channels.values())

    async def get_channel(self, channel_id: int) -> Channel | None:
        return self._channels.get(channel_id)

    async def set_global_interests(self, interests: Sequence[Interest]) -> None:
        self._interests = list(interests)

    async def global_interests(self) -> list[Interest]:
        return list(self._interests)

    async def get_watermark(self, channel_id: int) -> datetime | None:
        return self._watermarks.get(channel_id)

    async def set_watermark(self, channel_id: int, value: datetime) -> None:
        self._watermarks[channel_id] = value

    async def enqueue_report(self, verdict: Verdict) -> None:
        self._queue[self._next_queue] = verdict
        self._next_queue += 1

    async def peek_report_queue(self) -> list[tuple[int, Verdict]]:
        return list(self._queue.items())

    async def ack_report(self, ids: Sequence[int]) -> None:
        for item_id in ids:
            self._queue.pop(item_id, None)

    async def seen_signatures(self, signatures: set[str], since: datetime) -> set[str]:
        return {sig for sig in signatures if sig in self._seen and self._seen[sig] >= since}

    async def record_seen(self, signatures: set[str], when: datetime) -> None:
        self._seen.update(dict.fromkeys(signatures, when))

    async def log_cost(self, entry: CostEntry) -> None:
        self._costs.append(entry)

    async def total_cost(self) -> float:
        return sum(e.cost or 0 for e in self._costs)

    async def upsert_source(self, telegram_id: int) -> Source:
        if telegram_id not in self._source_ids:
            source = Source(len(self._sources) + 1, telegram_id)
            self._sources[source.id] = source
            self._source_ids[telegram_id] = source.id
        return self._sources[self._source_ids[telegram_id]]

    async def get_source(self, source_id: int) -> Source | None:
        return self._sources.get(source_id)

    async def upsert_rss_source(self, url: str) -> Source:
        if url not in self._rss_source_ids:
            source = Source(len(self._sources) + 1, rss_url=url)
            self._sources[source.id] = source
            self._rss_source_ids[url] = source.id
        return self._sources[self._rss_source_ids[url]]

    async def store_items(self, source_id: int, items: Sequence[Item]) -> None:
        for item in items:
            self._items[source_id, item.external_id] = item

    async def read_window(self, source_id: int, start: datetime, end: datetime) -> list[Item]:
        return sorted(
            (
                i
                for (sid, _), i in self._items.items()
                if sid == source_id and start <= i.timestamp <= end
            ),
            key=lambda i: i.timestamp,
        )

    async def count_window(self, source_id: int, start: datetime, end: datetime) -> int:
        return sum(
            sid == source_id and start <= item.timestamp <= end
            for (sid, _), item in self._items.items()
        )

    async def read_window_page(
        self,
        source_id: int,
        start: datetime,
        end: datetime,
        *,
        after: tuple[datetime, str] | None,
        limit: int,
    ) -> list[Item]:
        if limit < 1:
            raise ValueError("Page limit must be positive")
        return sorted(
            (
                item
                for (sid, _), item in self._items.items()
                if sid == source_id
                and start <= item.timestamp <= end
                and (after is None or (item.timestamp, item.external_id) > after)
            ),
            key=lambda item: (item.timestamp, item.external_id),
        )[:limit]

    async def coverage(self, source_id: int, start: datetime, end: datetime) -> Coverage:
        return coverage_for_window(self._coverage.get(source_id, []), start, end)

    async def mark_coverage(
        self, source_id: int, start: datetime, end: datetime, complete: bool
    ) -> None:
        self._coverage.setdefault(source_id, []).append(Coverage(start, end, complete))

    async def get_ingest_watermark(self, source_id: int) -> datetime | None:
        return self._ingest_watermarks.get(source_id)

    async def set_ingest_watermark(self, source_id: int, value: datetime) -> None:
        self._ingest_watermarks[source_id] = value
