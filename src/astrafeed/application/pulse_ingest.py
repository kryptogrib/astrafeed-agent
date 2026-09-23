"""Resumable, duplicate-free collection of discussion comments.

For every post in the window the collector asks Telegram for the thread's reply
counter (100 posts per request) and rereads a thread only when needed:

* counter is 0            -> EMPTY, nothing to read;
* counter equals the one stored at the last settled scan -> skip;
* anything else (new post, late comments, previous flood-wait/error/truncation)
  -> read the whole thread and upsert every comment.

Comments are keyed by ``discussion_peer:comment_id``, so rereading a thread
never duplicates rows. A flood-wait or error is stored as such, with the old
counter kept, and is never recorded as "0 comments"; the next run retries it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from astrafeed.domain.models import CommentFetch, CommentStatus, Item
from astrafeed.domain.pulse import StoredComment, ThreadState
from astrafeed.ports.ingestion import IngestionStore
from astrafeed.ports.pulse import CommentStore, ThreadReader

_log = logging.getLogger(__name__)

# Threads above this are marked possibly_truncated by the reader and rescanned.
THREAD_LIMIT = 5000


@dataclass
class ChannelCommentReport:
    ref: str
    posts: int = 0
    with_comments: int = 0
    scanned: int = 0
    skipped: int = 0
    failed: int = 0
    truncated: int = 0
    comments: int = 0
    error: str = ""
    failures: list[str] = field(default_factory=list)


def comment_link(channel_ref: str, post_id: str, comment_id: str) -> str:
    return f"https://t.me/{channel_ref.lstrip('@')}/{post_id}?comment={comment_id}"


def stored_comments(source_id: int, item: Item, fetch: CommentFetch) -> list[StoredComment]:
    rows = []
    for c in fetch.comments:
        peer = c.peer_id or fetch.discussion_peer_id or item.channel_ref
        parent = c.reply_to_id if c.reply_to_id != fetch.root_id else None
        rows.append(
            StoredComment(
                comment_key=f"{peer}:{c.external_id}",
                source_id=source_id,
                post_id=item.external_id,
                comment_id=c.external_id,
                ts=c.timestamp,
                text=c.text,
                link=comment_link(item.channel_ref, item.external_id, c.external_id),
                parent_comment_id=parent,
                edited_at=c.edited_at,
                author_key=c.author_key,
                has_media=c.has_media,
            )
        )
    return rows


class CommentCollector:
    def __init__(
        self,
        posts: IngestionStore,
        comments: CommentStore,
        reader: ThreadReader,
        *,
        now: Callable[[], datetime] | None = None,
        thread_limit: int = THREAD_LIMIT,
    ) -> None:
        self._posts = posts
        self._comments = comments
        self._reader = reader
        self._now = now or (lambda: datetime.now(UTC))
        self._thread_limit = thread_limit

    async def collect(
        self, sources: Sequence[tuple[int, str]], start: datetime, end: datetime
    ) -> list[ChannelCommentReport]:
        """Collect each ``(source_id, channel_ref)``; a failing channel never stops the rest."""
        reports = []
        for source_id, ref in sources:
            report = ChannelCommentReport(ref=ref)
            try:
                await self._collect_channel(source_id, ref, start, end, report)
            except Exception as e:  # noqa: BLE001 - report per channel and keep going
                _log.warning("comment collection failed for %s: %s", ref, e)
                report.error = str(e)
            reports.append(report)
        return reports

    async def _collect_channel(
        self,
        source_id: int,
        ref: str,
        start: datetime,
        end: datetime,
        report: ChannelCommentReport,
    ) -> None:
        items = await self._posts.read_window(source_id, start, end)
        items.sort(key=lambda i: i.timestamp, reverse=True)
        report.posts = len(items)
        if not items:
            return
        counters = await self._reader.reply_counts(ref, [i.external_id for i in items])
        states = await self._comments.thread_states(source_id)
        for item in items:
            counter = counters.get(item.external_id)
            previous = states.get(item.external_id)
            if counter:
                report.with_comments += 1
            if counter is None or counter == 0:
                # No discussion attached, or nobody commented: settled without a read.
                status = CommentStatus.UNAVAILABLE if counter is None else CommentStatus.EMPTY
                if previous is None or previous.status is not status:
                    await self._comments.save_thread(
                        ThreadState(source_id, item.external_id, status, counter, 0, self._now()),
                        (),
                    )
                report.skipped += 1
                continue
            if previous is not None and previous.settled and previous.reply_counter == counter:
                report.skipped += 1
                report.comments += previous.comments_stored
                continue
            fetch = await self._reader.fetch_comments_detailed(
                item, limit=self._thread_limit, parent_limit=0
            )
            rows = stored_comments(source_id, item, fetch)
            finished = fetch.status not in (CommentStatus.FLOOD_WAIT, CommentStatus.ERROR)
            kept = getattr(previous, "comments_stored", 0)
            state = ThreadState(
                source_id=source_id,
                post_id=item.external_id,
                status=fetch.status,
                # Keep the old counter on failure so the next run rereads the thread.
                reply_counter=counter if finished else getattr(previous, "reply_counter", None),
                comments_stored=len(rows) if finished else max(len(rows), kept),
                last_scan_at=self._now(),
                possibly_truncated=fetch.possibly_truncated,
                context_incomplete=fetch.context_incomplete,
                reason=fetch.reason,
            )
            await self._comments.save_thread(state, rows)
            report.scanned += 1
            report.comments += state.comments_stored
            report.truncated += fetch.possibly_truncated
            if not finished:
                report.failed += 1
                report.failures.append(f"{item.external_id}:{fetch.status.value}")
                if fetch.status is CommentStatus.FLOOD_WAIT:
                    # Leave the rest of this channel for the next run instead of hammering it.
                    report.error = f"flood wait at post {item.external_id}: {fetch.reason}"
                    return
