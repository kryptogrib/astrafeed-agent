"""Read a prepared IngestionStore window as a personal Pipeline Source."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from astrafeed.domain import Channel, Item, Subscription
from astrafeed.domain.progress import processed_item_signature
from astrafeed.ports import Repository
from astrafeed.ports.ingestion import IngestionStore


class WindowSource:
    """Maps shared raw items onto the calling user's Channel.telegram_ref."""

    def __init__(
        self,
        store: IngestionStore,
        *,
        repo: Repository | None = None,
        max_posts_per_channel: int = 200,
        max_posts_per_run: int = 1000,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> None:
        self._repo = repo
        self._channel_limit = max_posts_per_channel
        self._run_limit = max_posts_per_run
        self._remaining = max_posts_per_run
        self.truncated = False
        self._store = store
        self._start = start
        self._end = end

    def bind_window(self, start: datetime, end: datetime) -> None:
        self._remaining = self._run_limit
        self.truncated = False
        self._start = start
        self._end = end

    async def fetch_new_items(self, channel: Channel, since: datetime | None) -> list[Item]:
        if channel.source_id is None or self._start is None or self._end is None:
            return []
        limit = min(self._channel_limit, self._remaining)
        page_size = 200 if since is not None and self._repo is not None else min(200, limit + 1)
        page_size = max(1, page_size)
        start = max(self._start, since) if since is not None else self._start
        after: tuple[datetime, str] | None = None
        mapped: list[Item] = []
        while len(mapped) <= limit:
            page = await self._store.read_window_page(
                channel.source_id, start, self._end, after=after, limit=page_size
            )
            if not page:
                break
            seen: set[str] = set()
            if since is not None and self._repo is not None and channel.id is not None:
                keys = {
                    processed_item_signature(channel.id, item.external_id)
                    for item in page
                    if item.timestamp == since
                }
                if keys:
                    seen = await self._repo.seen_signatures(keys, since)
            for item in page:
                if item.timestamp == since:
                    if self._repo is None or channel.id is None:
                        continue
                    if processed_item_signature(channel.id, item.external_id) in seen:
                        continue
                mapped.append(
                    replace(item, channel_ref=channel.telegram_ref, channel_name=channel.name)
                )
                if len(mapped) > limit:
                    break
            if len(page) < page_size:
                break
            after = (page[-1].timestamp, page[-1].external_id)
        selected = mapped[:limit]
        self.truncated |= len(mapped) > limit
        self._remaining -= len(selected)
        return selected

    async def list_subscribed_channels(self) -> list[Subscription]:
        return []
