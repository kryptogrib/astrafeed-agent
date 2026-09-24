"""Collect configured feeds into the shared publication cache."""

from __future__ import annotations

import logging
from datetime import datetime

from astrafeed.adapters.source.rss import RssReader
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
        try:
            items = await reader.read(url)
            in_window = [item for item in items if start <= item.timestamp <= end]
            await store.store_items(source_id, in_window)
            # A feed only exposes a rolling tail. The oldest entry must reach
            # the window start before we can claim the full interval was seen.
            complete = bool(items) and items[0].timestamp <= start
            await store.mark_coverage(source_id, start, end, complete=complete)
            if not complete:
                errors[source_id] = "feed history does not reach window start"
        except Exception as exc:  # noqa: BLE001 - one bad publisher must not stop siblings
            errors[source_id] = f"{type(exc).__name__}: {exc}"
            await store.mark_coverage(source_id, start, end, complete=False)
        if source_id in errors:
            _log.warning("RSS source %s incomplete: %s", url, errors[source_id])
    return errors
