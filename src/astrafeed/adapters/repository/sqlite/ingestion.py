from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import inspect, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from astrafeed.adapters.repository.sqlite.models import (
    RawItemRow,
    SourceCoverageRow,
    SourceIngestionStateRow,
    SourceRow,
)
from astrafeed.domain.ingestion import Coverage, Source, coverage_for_window
from astrafeed.domain.models import Item


async def migrate_rss_sources(connection) -> None:
    """Add RSS identity to an existing Telegram-only source catalog."""
    columns = await connection.run_sync(
        lambda sync: {column["name"] for column in inspect(sync).get_columns("source")}
    )
    if "rss_url" not in columns:
        await connection.exec_driver_sql("ALTER TABLE source ADD COLUMN rss_url VARCHAR")
    await connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_source_rss_url ON source (rss_url)"
    )


def _encode_item(item: Item) -> dict[str, object]:
    return {
        "channel_ref": item.channel_ref,
        "external_id": item.external_id,
        "text": item.text,
        "link": item.link,
        "timestamp": item.timestamp.isoformat(),
        "has_media": item.has_media,
        "channel_name": item.channel_name,
    }


def _decode_item(value: dict[str, object]) -> Item:
    return Item(
        channel_ref=str(value["channel_ref"]),
        external_id=str(value["external_id"]),
        text=str(value["text"]),
        link=str(value["link"]),
        timestamp=datetime.fromisoformat(str(value["timestamp"])),
        has_media=bool(value.get("has_media", False)),
        channel_name=(str(value["channel_name"]) if value.get("channel_name") else None),
    )


def _source_from_row(row: SourceRow) -> Source:
    return Source(
        id=row.id,
        telegram_id=None if row.rss_url else row.telegram_id,
        rss_url=row.rss_url,
    )


class SqliteIngestionStore:
    """Shared source catalog and raw cache. No Telegram I/O."""

    def __init__(self, session: async_sessionmaker) -> None:
        self._session = session

    async def upsert_source(self, telegram_id: int) -> Source:
        async with self._session() as s, s.begin():
            existing = await s.scalar(select(SourceRow).where(SourceRow.telegram_id == telegram_id))
            if existing is not None:
                return _source_from_row(existing)
            row = SourceRow(telegram_id=telegram_id)
            s.add(row)
            await s.flush()
            return _source_from_row(row)

    async def upsert_rss_source(self, url: str) -> Source:
        async with self._session() as s, s.begin():
            existing = await s.scalar(select(SourceRow).where(SourceRow.rss_url == url))
            if existing is not None:
                return _source_from_row(existing)
            # Existing databases have telegram_id NOT NULL. A stable negative
            # catalog key leaves that schema intact; rss_url is the real identity.
            surrogate = -int.from_bytes(hashlib.sha256(url.encode()).digest()[:7], "big") - 1
            row = SourceRow(telegram_id=surrogate, rss_url=url)
            s.add(row)
            await s.flush()
            return _source_from_row(row)

    async def get_source(self, source_id: int) -> Source | None:
        async with self._session() as s:
            row = await s.get(SourceRow, source_id)
            return _source_from_row(row) if row is not None else None

    async def _require_source(self, s, source_id: int) -> SourceRow:
        row = await s.get(SourceRow, source_id)
        if row is None:
            raise LookupError(f"source {source_id} not found")
        return row

    async def store_items(self, source_id: int, items: Sequence[Item]) -> None:
        async with self._session() as s, s.begin():
            await self._require_source(s, source_id)
            for item in items:
                payload = json.dumps(_encode_item(item))
                stmt = sqlite_insert(RawItemRow).values(
                    source_id=source_id,
                    external_id=item.external_id,
                    timestamp=item.timestamp,
                    payload=payload,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[RawItemRow.source_id, RawItemRow.external_id],
                    set_={"timestamp": item.timestamp, "payload": payload},
                )
                await s.execute(stmt)

    async def read_window(self, source_id: int, start: datetime, end: datetime) -> list[Item]:
        async with self._session() as s:
            rows = (
                await s.scalars(
                    select(RawItemRow)
                    .where(
                        RawItemRow.source_id == source_id,
                        RawItemRow.timestamp >= start,
                        RawItemRow.timestamp <= end,
                    )
                    .order_by(RawItemRow.timestamp, RawItemRow.external_id)
                )
            ).all()
            return [_decode_item(json.loads(r.payload)) for r in rows]

    async def coverage(self, source_id: int, start: datetime, end: datetime) -> Coverage:
        async with self._session() as s:
            rows = (
                await s.scalars(
                    # Spans outside the window cannot help cover it; the table
                    # gains a row per source per cycle, so never read them all.
                    select(SourceCoverageRow).where(
                        SourceCoverageRow.source_id == source_id,
                        SourceCoverageRow.complete.is_(True),
                        SourceCoverageRow.end >= start,
                        SourceCoverageRow.start <= end,
                    )
                )
            ).all()
            records = [Coverage(start=r.start, end=r.end, complete=r.complete) for r in rows]
        return coverage_for_window(records, start, end)

    async def mark_coverage(
        self, source_id: int, start: datetime, end: datetime, complete: bool
    ) -> None:
        async with self._session() as s, s.begin():
            await self._require_source(s, source_id)
            stmt = sqlite_insert(SourceCoverageRow).values(
                source_id=source_id,
                start=start,
                end=end,
                complete=complete,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    SourceCoverageRow.source_id,
                    SourceCoverageRow.start,
                    SourceCoverageRow.end,
                ],
                set_={"complete": complete},
            )
            await s.execute(stmt)

    async def get_ingest_watermark(self, source_id: int) -> datetime | None:
        async with self._session() as s:
            row = await s.get(SourceIngestionStateRow, source_id)
            return None if row is None else row.last_seen

    async def set_ingest_watermark(self, source_id: int, value: datetime) -> None:
        async with self._session() as s, s.begin():
            await self._require_source(s, source_id)
            stmt = sqlite_insert(SourceIngestionStateRow).values(
                source_id=source_id, last_seen=value
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[SourceIngestionStateRow.source_id],
                set_={"last_seen": value},
            )
            await s.execute(stmt)
