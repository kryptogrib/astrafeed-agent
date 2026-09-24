"""Read selected X replies once, keeping them separate from story votes."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol

from astrafeed.domain.models import DiscussionComment, Item
from astrafeed.ports.agenda import CommentReader

MAX_FETCHED_THREADS = 70
MAX_THREADS_PER_HOUR = 3


class XpozReplyReader(Protocol):
    async def comments(self, post_id: str) -> tuple[list[object], bool]: ...


class XpozThreadCache(Protocol):
    async def reply_counts(self, post_ids: Sequence[str]) -> dict[str, int]: ...
    async def cached_comments(self, post_id: str) -> list[DiscussionComment] | None: ...
    async def fetched_count(self) -> int: ...
    async def recent_fetch_count(self, since: datetime) -> int: ...
    async def save_comments(
        self, post_id: str, comments: Sequence[DiscussionComment], truncated: bool
    ) -> None: ...


class XpozComments:
    def __init__(self, reader: XpozReplyReader, cache: XpozThreadCache) -> None:
        self._reader = reader
        self._cache = cache

    async def reply_counts(self, channel_ref: str, post_ids: Sequence[str]) -> dict[str, int]:
        return await self._cache.reply_counts(post_ids)

    async def fetch_comments(self, item: Item, *, limit: int) -> list[DiscussionComment]:
        cached = await self._cache.cached_comments(item.external_id)
        if cached is not None:
            return cached[:limit]
        if await self._cache.fetched_count() >= MAX_FETCHED_THREADS:
            return []
        if (
            await self._cache.recent_fetch_count(datetime.now(UTC) - timedelta(hours=1))
            >= MAX_THREADS_PER_HOUR
        ):
            return []
        # Record the attempt before making a paid call. A timeout can still
        # consume credits, so it must count against both persistent caps.
        await self._cache.save_comments(item.external_id, [], False)
        raw, truncated = await self._reader.comments(item.external_id)
        found: list[DiscussionComment] = []
        for post in raw:
            post_id = str(getattr(post, "id", "") or "")
            text = str(getattr(post, "text", "") or "").strip()
            author = str(getattr(post, "author_username", "") or "").lstrip("@")
            when = getattr(post, "created_at", None)
            if isinstance(when, str):
                try:
                    when = datetime.fromisoformat(when.replace("Z", "+00:00"))
                except ValueError:
                    continue
            if not post_id or not text or not isinstance(when, datetime):
                continue
            when = when.replace(tzinfo=UTC) if when.tzinfo is None else when.astimezone(UTC)
            found.append(
                DiscussionComment(
                    external_id=post_id,
                    text=text,
                    timestamp=when,
                    link=f"https://x.com/{author}/status/{post_id}" if author else "",
                    author_key=author or None,
                    reply_to_id=getattr(post, "reply_to_tweet_id", None),
                )
            )
        await self._cache.save_comments(item.external_id, found, truncated)
        return found[:limit]


class CompositeComments:
    def __init__(self, telegram: CommentReader, xpoz: XpozComments) -> None:
        self._telegram = telegram
        self._xpoz = xpoz

    async def reply_counts(self, channel_ref: str, post_ids: Sequence[str]) -> dict[str, int]:
        if channel_ref.startswith("x/@"):
            return await self._xpoz.reply_counts(channel_ref, post_ids)
        return await self._telegram.reply_counts(channel_ref, post_ids)

    async def fetch_comments(self, item: Item, *, limit: int) -> list[DiscussionComment]:
        if item.channel_ref.startswith("x/@"):
            return await self._xpoz.fetch_comments(item, limit=limit)
        return await self._telegram.fetch_comments(item, limit=limit)
