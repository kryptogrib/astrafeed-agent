from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from astrafeed.domain import (
    Channel,
    CommentFetch,
    CommentStatus,
    DiscussionComment,
    Item,
    Subscription,
)
from astrafeed.domain.refs import normalize_channel_ref

CommentKey = tuple[str, str]

_log = logging.getLogger(__name__)


class _LiveReader(Protocol):
    async def fetch_comments_detailed(
        self, item: Item, *, limit: int, parent_limit: int = 0
    ) -> CommentFetch: ...


def _key(ref: str) -> str:
    return normalize_channel_ref(ref).lower()


class CachedSource:
    """Replays a pre-fetched snapshot offline, bounded by a movable ``window_end``.

    Implements the ``Source`` port so it drops straight into ``Pipeline``. Each
    simulated tick the harness advances ``window_end``; ``fetch_new_items`` then
    returns items with ``since < timestamp <= window_end`` (strict lower bound,
    matching Telegram's ``msg.date > floor``), oldest-first.

    When seeded with ``comments_by_key`` it also satisfies the ``DiscussionReader``
    port, so the report stage enriches discussions fully offline — mirroring
    production, where ``TelegramSource`` is both ``Source`` and ``DiscussionReader``.
    """

    def __init__(
        self,
        items_by_ref: dict[str, list[Item]],
        *,
        comments_by_key: dict[CommentKey, CommentFetch] | None = None,
        observer: Callable[..., None] | None = None,
        live_reader: _LiveReader | None = None,
        discussion_join_budget: int | None = None,
    ) -> None:
        self._items_by_ref: dict[str, list[Item]] = {}
        for ref, items in items_by_ref.items():
            self._items_by_ref.setdefault(_key(ref), []).extend(items)
        self._comments_by_key: dict[CommentKey, CommentFetch] = comments_by_key or {}
        self._observer = observer
        # Cache-miss safety net (issue-10): the prefetch and the live report each run
        # an INDEPENDENT non-deterministic importance scoring over two different DBs,
        # so the report can request a discussion candidate the prefetch never captured.
        # Rather than silently return [] (the old cache_miss), fill the gap live when a
        # reader is wired, bounded by a PER-REPORT join budget. A candidate skipped
        # because the budget is spent is classified ``stated_budget`` (deliberate), not
        # ``cache_miss`` (defect). ``None`` budget = unbounded.
        self._live_reader = live_reader
        self._discussion_join_budget = discussion_join_budget
        self._joins_left = discussion_join_budget
        # The harness sets these before each tick. window_start is the run floor
        # (now - days) so the first tick (since=None) still honours "last N days".
        self.window_start: datetime | None = None
        self.window_end: datetime | None = None

    async def fetch_new_items(self, channel: Channel, since: datetime | None) -> list[Item]:
        items = self._items_by_ref.get(_key(channel.telegram_ref), [])
        out = [
            i
            for i in items
            if (since is None or i.timestamp > since)
            and (self.window_start is None or i.timestamp > self.window_start)
            and (self.window_end is None or i.timestamp <= self.window_end)
        ]
        return sorted(out, key=lambda i: i.timestamp)

    async def list_subscribed_channels(self) -> list[Subscription]:
        return []

    @property
    def comments_cache(self) -> dict[CommentKey, CommentFetch]:
        """The live comment cache, including any entries filled live during replay.
        Lets the harness persist a live-augmented cache back to ``comments.jsonl``."""
        return self._comments_by_key

    def reset_discussion_join_budget(self) -> None:
        """Refill the PER-REPORT live-fill budget. The report stage calls this at the
        top of each report (``_run_narrative`` / ``_enrich_discussions``), so the
        budget is counted per report, never accumulated across the whole run."""
        self._joins_left = self._discussion_join_budget

    async def fetch_comments(self, item: Item, *, limit: int) -> list[DiscussionComment]:
        """Serve cached discussion comments offline (the ``DiscussionReader`` port).

        Thin wrapper over :meth:`fetch_comments_detailed`: only a ``FETCHED``/
        ``EMPTY`` result yields data (sliced to ``limit``), everything else
        (a cached transient status, ``stated_budget``, ``cache_miss``) returns
        ``[]``. Behaviour unchanged from before ``fetch_comments_detailed``
        existed as a separate method.
        """
        fetch = await self.fetch_comments_detailed(item, limit=limit)
        if fetch.status in (CommentStatus.FETCHED, CommentStatus.EMPTY):
            return list(fetch.comments[:limit])
        return []

    async def fetch_comments_detailed(
        self, item: Item, *, limit: int, parent_limit: int = 0
    ) -> CommentFetch:
        """Serve a full ``CommentFetch`` offline, live-filling on a genuine miss.

        * A cache hit is returned as-is (the stored ``CommentFetch``, including
          its ``context_incomplete``/``possibly_truncated``/``missing_parent_ids``
          fields from whatever produced it) — the observer sees ``cache_hit``.
        * Budget exhausted → a synthesized ``UNAVAILABLE`` fetch, classified
          ``stated_budget`` (deliberately not fetched), logged.
        * A live reader is wired → ``live_fetch`` fills the gap, forwarding
          ``parent_limit`` through, and the full result is cached verbatim.
        * Otherwise → a synthesized ``UNAVAILABLE`` fetch, classified
          ``cache_miss`` (the residual defect, target 0).
        """
        key = (_key(item.channel_ref), item.external_id)
        entry = self._comments_by_key.get(key)
        if entry is not None:
            self._emit("cache_hit", item=item, status=entry.status, raw_count=entry.raw_count)
            return entry

        if (
            self._discussion_join_budget is not None
            and self._joins_left is not None
            and (self._joins_left <= 0)
        ):
            _log.info(
                "discussion join budget exhausted; not fetching %s/%s (stated_budget)",
                item.channel_ref,
                item.external_id,
            )
            self._emit("stated_budget", item=item)
            return CommentFetch(
                status=CommentStatus.UNAVAILABLE, limit=limit, reason="stated_budget"
            )

        if self._live_reader is not None:
            if self._joins_left is not None:
                self._joins_left -= 1
            fetch = await self._live_reader.fetch_comments_detailed(
                item, limit=limit, parent_limit=parent_limit
            )
            # Cache the live result so a re-request (or a later tick) is served offline
            # and the snapshot store can persist it as a real comments.jsonl record.
            self._comments_by_key[key] = fetch
            self._emit("live_fetch", item=item, status=fetch.status, raw_count=fetch.raw_count)
            return fetch

        self._emit("cache_miss", item=item)
        return CommentFetch(status=CommentStatus.UNAVAILABLE, limit=limit, reason="cache_miss")

    def _emit(self, event: str, **fields) -> None:
        if self._observer is not None:
            self._observer(event=event, **fields)
