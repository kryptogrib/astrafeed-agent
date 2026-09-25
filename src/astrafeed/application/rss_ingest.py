"""Collect configured feeds into the shared publication cache."""

from __future__ import annotations

import logging
from datetime import datetime

from astrafeed.adapters.source.rss import RssReader
from astrafeed.domain.ingestion import FRESH_POST_WINDOW
from astrafeed.ports.ingestion import IngestionStore

_log = logging.getLogger(__name__)


async def resolve_feeds(store: IngestionStore, urls: list[str]) -> dict[int, str]:
    return {
        source.id: url
        for url in dict.fromkeys(urls)
        for source in [await store.upsert_rss_source(url)]
    }


async def collect_feeds(
    store: IngestionStore,
    reader: RssReader,
    feeds: dict[int, str],
    start: datetime,
    end: datetime,
) -> dict[int, str]:
    """Store available articles; report missing history and fetch failures per feed."""
    errors: dict[int, str] = {}
    for source_id, url in feeds.items():
        last = await store.get_ingest_watermark(source_id)
        read_start = max(start, end - FRESH_POST_WINDOW, last or start)
        try:
            items = await reader.read(url)
            in_window = [
                item
                for item in items
                if read_start <= item.timestamp <= end and (last is None or item.timestamp > last)
            ]
            await store.store_items(source_id, in_window)
            # A feed only exposes a rolling tail. The oldest entry must reach
            # the window start before we can claim the full interval was seen.
            complete = bool(items) and items[0].timestamp <= read_start
            await store.mark_coverage(source_id, read_start, end, complete=complete)
            await store.set_ingest_watermark(source_id, end)
            if not complete:
                errors[source_id] = "feed history does not reach window start"
        except Exception as exc:  # noqa: BLE001 - one bad publisher must not stop siblings
            errors[source_id] = f"{type(exc).__name__}: {exc}"
            await store.mark_coverage(source_id, read_start, end, complete=False)
        if source_id in errors:
            _log.warning("RSS source %s incomplete: %s", url, errors[source_id])
    return errors
