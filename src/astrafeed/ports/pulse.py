from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from astrafeed.domain.models import CommentFetch, Item
from astrafeed.domain.pulse import StoredComment, ThreadState


class CommentStore(Protocol):
    """Discussion comments and per-thread scan state. Writes are idempotent upserts."""

    async def save_thread(self, state: ThreadState, comments: Sequence[StoredComment]) -> None: ...
    async def thread_states(
        self, source_id: int, post_ids: Sequence[str]
    ) -> dict[str, ThreadState]: ...
    async def read_comments(
        self, source_id: int, start: datetime, end: datetime
    ) -> list[StoredComment]: ...


class ThreadReader(Protocol):
    """Telegram side of comment collection."""

    async def reply_counts(self, channel_ref: str, post_ids: Sequence[str]) -> dict[str, int]: ...
    async def fetch_comments_detailed(
        self, item: Item, *, limit: int, parent_limit: int = 0
    ) -> CommentFetch: ...
