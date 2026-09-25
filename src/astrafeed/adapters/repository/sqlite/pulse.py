from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import case, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from astrafeed.adapters.repository.sqlite.models import CommentRow, ThreadStateRow
from astrafeed.domain.models import CommentStatus
from astrafeed.domain.pulse import StoredComment, ThreadState


def _comment(row: CommentRow) -> StoredComment:
    return StoredComment(
        comment_key=row.comment_key,
        source_id=row.source_id,
        post_id=row.post_id,
        comment_id=row.comment_id,
        ts=row.ts,
        text=row.text,
        link=row.link,
        parent_comment_id=row.parent_comment_id,
        edited_at=row.edited_at,
        author_key=row.author_key,
        has_media=row.has_media,
    )


def _state(row: ThreadStateRow) -> ThreadState:
    return ThreadState(
        source_id=row.source_id,
        post_id=row.post_id,
        status=CommentStatus(row.status),
        reply_counter=row.reply_counter,
        comments_stored=row.comments_stored,
        last_scan_at=row.last_scan_at,
        possibly_truncated=row.possibly_truncated,
        context_incomplete=row.context_incomplete,
        reason=row.reason,
    )


class SqliteCommentStore:
    def __init__(self, session: async_sessionmaker) -> None:
        self._session = session

    async def save_thread(self, state: ThreadState, comments: Sequence[StoredComment]) -> None:
        """Upsert the comments and the thread state in one transaction."""
        async with self._session() as s, s.begin():
            if comments:
                comment_values = [
                    {
                        "comment_key": c.comment_key,
                        "source_id": c.source_id,
                        "post_id": c.post_id,
                        "comment_id": c.comment_id,
                        "parent_comment_id": c.parent_comment_id,
                        "ts": c.ts,
                        "edited_at": c.edited_at,
                        "text": c.text,
                        "link": c.link,
                        "author_key": c.author_key,
                        "has_media": c.has_media,
                    }
                    for c in comments
                ]
                stmt = sqlite_insert(CommentRow)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[CommentRow.comment_key],
                    set_={
                        **{k: stmt.excluded[k] for k in comment_values[0] if k != "comment_key"},
                        # An edited comment must be classified again.
                        "classified": case(
                            (CommentRow.text != stmt.excluded.text, False),
                            else_=CommentRow.classified,
                        ),
                    },
                )
                await s.execute(stmt, comment_values)
            state_values = {
                "source_id": state.source_id,
                "post_id": state.post_id,
                "status": state.status.value,
                "reply_counter": state.reply_counter,
                "comments_stored": state.comments_stored,
                "possibly_truncated": state.possibly_truncated,
                "context_incomplete": state.context_incomplete,
                "reason": state.reason,
                "last_scan_at": state.last_scan_at,
            }
            stmt = sqlite_insert(ThreadStateRow).values(**state_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[ThreadStateRow.source_id, ThreadStateRow.post_id],
                set_={
                    k: stmt.excluded[k] for k in state_values if k not in ("source_id", "post_id")
                },
            )
            await s.execute(stmt)

    async def thread_states(
        self, source_id: int, post_ids: Sequence[str]
    ) -> dict[str, ThreadState]:
        if not post_ids:
            return {}
        async with self._session() as s:
            rows = []
            for offset in range(0, len(post_ids), 500):
                rows.extend(
                    (
                        await s.scalars(
                            select(ThreadStateRow).where(
                                ThreadStateRow.source_id == source_id,
                                ThreadStateRow.post_id.in_(post_ids[offset : offset + 500]),
                            )
                        )
                    ).all()
                )
        return {r.post_id: _state(r) for r in rows}

    async def read_comments(
        self, source_id: int, start: datetime, end: datetime
    ) -> list[StoredComment]:
        """Comments with ``start <= ts < end`` (half-open, like Pulse windows)."""
        async with self._session() as s:
            rows = (
                await s.scalars(
                    select(CommentRow)
                    .where(
                        CommentRow.source_id == source_id,
                        CommentRow.ts >= start,
                        CommentRow.ts < end,
                    )
                    .order_by(CommentRow.ts, CommentRow.comment_key)
                )
            ).all()
        return [_comment(r) for r in rows]
