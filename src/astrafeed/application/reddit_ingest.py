"""Read many subreddits in one RSS request while preserving source identities."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlparse

from astrafeed.adapters.source.rss import RssReader
from astrafeed.ports.ingestion import IngestionStore

_log = logging.getLogger(__name__)
_FEED_PATH = re.compile(r"^/r/([A-Za-z0-9_]+)/\.rss$", re.IGNORECASE)
_POST_PATH = re.compile(r"^/r/([A-Za-z0-9_]+)/comments/", re.IGNORECASE)


def _subreddit(url: str) -> str:
    parsed = urlparse(url)
    match = _FEED_PATH.fullmatch(parsed.path)
    if parsed.scheme != "https" or parsed.hostname not in {"reddit.com", "www.reddit.com"}:
        raise ValueError(f"Unsupported Reddit feed URL: {url}")
    if match is None or parsed.query or parsed.fragment:
        raise ValueError(f"Unsupported Reddit feed URL: {url}")
    return match.group(1)


async def resolve_reddit_feeds(store: IngestionStore, urls: list[str]) -> dict[int, str]:
    feeds: dict[int, str] = {}
    seen: set[str] = set()
    for url in urls:
        subreddit = _subreddit(url)
        if subreddit.casefold() in seen:
            continue
        seen.add(subreddit.casefold())
        source = await store.upsert_rss_source(url)
        feeds[source.id] = subreddit
    return feeds


def combined_url(subreddits: Mapping[int, str]) -> str:
    joined = "+".join(subreddits.values())
    return f"https://www.reddit.com/r/{joined}/new/.rss?limit=100"


async def collect_reddit_feeds(
    store: IngestionStore,
    reader: RssReader,
    feeds: dict[int, str],
    start: datetime,
    end: datetime,
) -> dict[int, str]:
    if not feeds:
        return {}
    by_name = {name.casefold(): (sid, name) for sid, name in feeds.items()}
    try:
        items = await reader.read(combined_url(feeds))
        grouped: dict[int, list] = {sid: [] for sid in feeds}
        for item in items:
            link = urlparse(item.link)
            match = _POST_PATH.match(link.path)
            if link.hostname not in {"reddit.com", "www.reddit.com"} or match is None:
                continue
            target = by_name.get(match.group(1).casefold())
            if target is None or not (start <= item.timestamp <= end):
                continue
            sid, subreddit = target
            grouped[sid].append(
                replace(item, channel_ref=f"r/{subreddit}", channel_name=f"r/{subreddit}")
            )
        complete = bool(items) and items[0].timestamp <= start
        for sid, posts in grouped.items():
            await store.store_items(sid, posts)
            await store.mark_coverage(sid, start, end, complete=complete)
        if complete:
            return {}
        return dict.fromkeys(feeds, "combined feed history does not reach window start")
    except Exception as exc:  # noqa: BLE001 - Reddit failure must not block other sources
        reason = f"{type(exc).__name__}: {exc}"
        _log.warning("Reddit RSS incomplete: %s", reason)
        for sid in feeds:
            await store.mark_coverage(sid, start, end, complete=False)
        return dict.fromkeys(feeds, reason)
