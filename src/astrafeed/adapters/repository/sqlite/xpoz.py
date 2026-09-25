"""Persistent X reply counts and once-only comment fetch cache."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from astrafeed.adapters.repository.sqlite.models import XpozThreadRow
from astrafeed.domain.models import DiscussionComment


class SqliteXpozThreads:
    def __init__(self, session: async_sessionmaker) -> None:
        self._session = session

    async def record_reply_counts(self, counts: Mapping[str, int]) -> None:
        async with self._session() as s, s.begin():
            pairs = list(counts.items())
            # SQLite also binds column defaults, so cap each statement below
            # the 999-variable limit supported by older installations.
            for offset in range(0, len(pairs), 150):
                stmt = sqlite_insert(XpozThreadRow).values(
                    [
                        {"post_id": post_id, "reply_count": count}
                        for post_id, count in pairs[offset : offset + 150]
                    ]
                )
                await s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[XpozThreadRow.post_id],
                        set_={"reply_count": stmt.excluded.reply_count},
                    )
                )

    async def reply_counts(self, post_ids: Sequence[str]) -> dict[str, int]:
        if not post_ids:
            return {}
        async with self._session() as s:
            result: dict[str, int] = {}
            for offset in range(0, len(post_ids), 500):
                rows = await s.execute(
                    select(XpozThreadRow.post_id, XpozThreadRow.reply_count).where(
                        XpozThreadRow.post_id.in_(post_ids[offset : offset + 500])
                    )
                )
                result.update(rows.all())
            return result

    async def cached_comments(self, post_id: str) -> list[DiscussionComment] | None:
        async with self._session() as s:
            row = await s.get(XpozThreadRow, post_id)
            if row is None or not row.fetched:
                return None
            return [
                DiscussionComment(
                    external_id=value["external_id"],
                    text=value["text"],
                    timestamp=datetime.fromisoformat(value["timestamp"]),
                    link=value["link"],
                    author_key=value.get("author_key"),
                    reply_to_id=value.get("reply_to_id"),
                )
                for value in json.loads(row.comments_json)
            ]

    async def fetched_count(self) -> int:
        async with self._session() as s:
            query = select(func.count()).select_from(XpozThreadRow).where(XpozThreadRow.fetched)
            return int(await s.scalar(query) or 0)

    async def recent_fetch_count(self, since: datetime) -> int:
        async with self._session() as s:
            query = (
                select(func.count())
                .select_from(XpozThreadRow)
                .where(XpozThreadRow.fetched_at >= since)
            )
            return int(await s.scalar(query) or 0)

    async def save_comments(
        self, post_id: str, comments: Sequence[DiscussionComment], truncated: bool
    ) -> None:
        payload = json.dumps(
            [
                {
                    "external_id": c.external_id,
                    "text": c.text,
                    "timestamp": c.timestamp.isoformat(),
                    "link": c.link,
                    "author_key": c.author_key,
                    "reply_to_id": c.reply_to_id,
                }
                for c in comments
            ]
        )
        async with self._session() as s, s.begin():
            fetched_at = datetime.now(UTC)
            stmt = sqlite_insert(XpozThreadRow).values(
                post_id=post_id,
                fetched=True,
                fetched_at=fetched_at,
                comments_json=payload,
                truncated=truncated,
            )
            await s.execute(
                stmt.on_conflict_do_update(
                    index_elements=[XpozThreadRow.post_id],
                    set_={
                        "fetched": True,
                        "fetched_at": fetched_at,
                        "comments_json": payload,
                        "truncated": truncated,
                    },
                )
            )
