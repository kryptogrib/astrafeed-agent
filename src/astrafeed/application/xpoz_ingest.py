"""Economical, best-effort collection of a broad X feed and selected accounts."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from astrafeed.domain.models import Item
from astrafeed.ports.ingestion import IngestionStore

_log = logging.getLogger(__name__)
RSS_ACCOUNTS = frozenset({"cointelegraph", "theblock__"})
ACCOUNT_INTERVAL = timedelta(hours=12)
SEARCH_INTERVAL = timedelta(minutes=15)
SEARCH_REF = "xpoz://search/crypto"


class XpozPostReader(Protocol):
    async def posts_by_author(self, handle: str, start: datetime) -> tuple[list[object], bool]: ...


class XpozSearchReader(Protocol):
    async def search_crypto(self, start: datetime) -> tuple[list[object], bool]: ...


class XpozReplyCountStore(Protocol):
    async def record_reply_counts(self, counts: Mapping[str, int]) -> None: ...


async def resolve_xpoz_accounts(store: IngestionStore, handles: Sequence[str]) -> dict[int, str]:
    accounts: dict[int, str] = {}
    seen: set[str] = set()
    for raw in handles:
        handle = raw.strip().lstrip("@")
        key = handle.casefold()
        if not handle or key in seen or key in RSS_ACCOUNTS:
            continue
        seen.add(key)
        # The existing external-source catalog uses rss_url as its stable URI
        # slot. This is a source identity, never passed to the RSS reader.
        source = await store.upsert_rss_source(f"xpoz://x.com/{key}")
        accounts[source.id] = handle
    return accounts


async def resolve_xpoz_search(store: IngestionStore) -> int:
    source = await store.upsert_rss_source(SEARCH_REF)
    return source.id


def _as_item(post: object, handle: str) -> Item | None:
    post_id = str(getattr(post, "id", "") or "")
    text = str(getattr(post, "text", "") or "").strip()
    when = getattr(post, "created_at", None)
    if isinstance(when, str):
        try:
            when = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(when, datetime) or not post_id or not text:
        return None
    if getattr(post, "is_retweet", False) or getattr(post, "reply_to_tweet_id", None):
        return None
    author = str(getattr(post, "author_username", None) or handle).lstrip("@")
    if author.casefold() != handle.casefold():
        return None
    when = when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)
    return Item(
        channel_ref=f"x/@{handle}",
        external_id=post_id,
        text=text,
        link=f"https://x.com/{author}/status/{post_id}",
        timestamp=when,
        channel_name=f"X @{handle}",
    )


async def collect_xpoz_accounts(
    store: IngestionStore,
    reader: XpozPostReader,
    accounts: Mapping[int, str],
    start: datetime,
    end: datetime,
    *,
    threads: XpozReplyCountStore | None = None,
) -> dict[int, str]:
    errors: dict[int, str] = {}
    for source_id, handle in accounts.items():
        last = await store.get_ingest_watermark(source_id)
        if last is not None and end - last < ACCOUNT_INTERVAL:
            continue
        query_start = max(start, last - timedelta(hours=1)) if last is not None else start
        try:
            raw_posts, truncated = await reader.posts_by_author(handle, query_start)
            items = [item for post in raw_posts if (item := _as_item(post, handle)) is not None]
            in_window = [i for i in items if start <= i.timestamp <= end]
            await store.store_items(source_id, in_window)
            if threads is not None:
                ids = {item.external_id for item in in_window}
                await threads.record_reply_counts(
                    {
                        str(getattr(post, "id", "")): max(
                            0, int(getattr(post, "reply_count", 0) or 0)
                        )
                        for post in raw_posts
                        if str(getattr(post, "id", "")) in ids
                    }
                )
            await store.set_ingest_watermark(source_id, end)
            # Xpoz's result coverage cannot prove full X coverage. Never turn
            # a missed/index-delayed post into measured zero activity.
            await store.mark_coverage(source_id, start, end, complete=False)
            if truncated:
                errors[source_id] = "Xpoz fast result reached its limit"
        except Exception as exc:  # noqa: BLE001 - one account must not block the others
            errors[source_id] = f"{type(exc).__name__}: {exc}"
            await store.mark_coverage(source_id, start, end, complete=False)
            _log.warning("Xpoz account %s incomplete: %s", handle, errors[source_id])
    return errors


async def collect_xpoz_search(
    store: IngestionStore,
    reader: XpozSearchReader,
    search_id: int,
    accounts: Mapping[int, str],
    start: datetime,
    end: datetime,
    *,
    threads: XpozReplyCountStore | None = None,
) -> str | None:
    last = await store.get_ingest_watermark(search_id)
    if last is not None and end - last < SEARCH_INTERVAL:
        return None
    query_start = max(start, last - timedelta(hours=2)) if last is not None else start
    by_handle = {handle.casefold(): sid for sid, handle in accounts.items()}
    try:
        raw_posts, truncated = await reader.search_crypto(query_start)
        grouped: dict[int, list[Item]] = {}
        counts: dict[str, int] = {}
        for post in raw_posts:
            author = str(getattr(post, "author_username", "") or "").lstrip("@")
            if not author or author.casefold() in RSS_ACCOUNTS:
                continue
            source_id = by_handle.get(author.casefold(), search_id)
            item = _as_item(post, author)
            if item is None or not (query_start <= item.timestamp <= end):
                continue
            grouped.setdefault(source_id, []).append(item)
            counts[item.external_id] = max(0, int(getattr(post, "reply_count", 0) or 0))
        for source_id, items in grouped.items():
            await store.store_items(source_id, items)
        if threads is not None:
            await threads.record_reply_counts(counts)
        await store.set_ingest_watermark(search_id, end)
        await store.mark_coverage(search_id, start, end, complete=False)
        return "Xpoz search fast result reached its limit" if truncated else None
    except Exception as exc:  # noqa: BLE001 - X discovery must not block other sources
        await store.mark_coverage(search_id, start, end, complete=False)
        reason = f"{type(exc).__name__}: {exc}"
        _log.warning("Xpoz crypto search incomplete: %s", reason)
        return reason
