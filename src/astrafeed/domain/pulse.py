"""Community Pulse storage records: stored comments and per-thread scan state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from astrafeed.domain.models import CommentStatus


@dataclass(frozen=True)
class StoredComment:
    """One discussion comment, keyed globally by ``discussion_peer:comment_id``.

    ``post_id`` is the channel post the thread hangs off; ``parent_comment_id``
    is the comment this one answers (None when it answers the post itself).
    """

    comment_key: str
    source_id: int
    post_id: str
    comment_id: str
    ts: datetime
    text: str
    link: str
    parent_comment_id: str | None = None
    edited_at: datetime | None = None
    author_key: str | None = None
    has_media: bool = False


@dataclass(frozen=True)
class ThreadState:
    """Completeness of the last scan of one post's thread.

    ``reply_counter`` is Telegram's own reply count at scan time. It is kept
    only for a scan that finished (FETCHED/EMPTY/UNAVAILABLE); a flood-wait or
    error keeps the previous counter so the next run rescans the thread.
    """

    source_id: int
    post_id: str
    status: CommentStatus
    reply_counter: int | None
    comments_stored: int
    last_scan_at: datetime
    possibly_truncated: bool = False
    context_incomplete: bool = False
    reason: str = ""

    @property
    def settled(self) -> bool:
        """The scan finished and read the whole thread as Telegram counted it."""
        return (
            self.status in (CommentStatus.FETCHED, CommentStatus.EMPTY, CommentStatus.UNAVAILABLE)
            and not self.possibly_truncated
        )
