"""SQLite persistence for agenda publications, reuse caches, and snapshots."""

from __future__ import annotations

import asyncio
import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from astrafeed.adapters.repository.sqlite.models import (
    AgendaCycleRow,
    AgendaFragmentRow,
    AgendaJsonRow,
    AgendaLinkRow,
    AgendaPublicationRow,
    AgendaQueueRow,
    AgendaSnapshotRow,
)
from astrafeed.domain.agenda import (
    SNAPSHOT_RETENTION,
    ChannelLead,
    Claim,
    ClaimCard,
    CommentQuote,
    CoverageInfo,
    CycleState,
    Discussion,
    Entity,
    Event,
    EventCard,
    ExtractedNumber,
    ExtractionResult,
    FigureGroup,
    Fragment,
    IndexedFragment,
    MentionedEntity,
    PositionCard,
    PriceAtPost,
    PriceMove,
    PublicationRef,
    PublicationVersion,
    SearchDoc,
    Snapshot,
    SourceNode,
    Story,
    StoryCard,
    StoryDetail,
    StoryLink,
    StorySignals,
    queue_reason_retryable,
)

_TYPES = {
    cls.__name__: cls
    for cls in (
        Claim,
        ClaimCard,
        CommentQuote,
        CoverageInfo,
        CycleState,
        Discussion,
        Entity,
        Event,
        EventCard,
        ExtractionResult,
        ExtractedNumber,
        Fragment,
        IndexedFragment,
        MentionedEntity,
        PositionCard,
        PublicationRef,
        PublicationVersion,
        SearchDoc,
        Snapshot,
        Story,
        StoryCard,
        StoryDetail,
        StoryLink,
        SourceNode,
        FigureGroup,
        PriceMove,
        PriceAtPost,
        StorySignals,
        ChannelLead,
    )
}


def encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__t__": "datetime", "v": value.isoformat()}
    if is_dataclass(value) and not isinstance(value, type):
        payload = {field.name: encode(getattr(value, field.name)) for field in fields(value)}
        payload["__t__"] = type(value).__name__
        return payload
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return {"__t__": "tuple", "v": [encode(item) for item in value]}
    if isinstance(value, list):
        return [encode(item) for item in value]
    return value


def decode(value: Any) -> Any:
    if isinstance(value, dict):
        kind = value.get("__t__")
        if kind == "datetime":
            return datetime.fromisoformat(value["v"])
        if kind == "tuple":
            return tuple(decode(item) for item in value["v"])
        if kind in _TYPES:
            data = {key: decode(item) for key, item in value.items() if key != "__t__"}
            return _TYPES[kind](**data)
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def dumps(value: Any) -> str:
    return json.dumps(encode(value), ensure_ascii=False)


def loads(raw: str) -> Any:
    return decode(json.loads(raw))


# SQLite's default bound-parameter limit is 999 on older builds.
_IN_CHUNK = 500


async def migrate_agenda_index_tables(connection: AsyncConnection) -> None:
    """Move links and fragments out of agenda_json into their indexed tables.

    Earlier releases stored them as untyped JSON rows, so every lookup read the
    whole history. Runs at startup; a no-op once agenda_json holds neither kind.
    """

    async def legacy(kind: str) -> list[tuple[str, str]]:
        query = select(AgendaJsonRow.item_id, AgendaJsonRow.payload)
        rows = await connection.execute(query.where(AgendaJsonRow.kind == kind))
        return [(item_id, payload) for item_id, payload in rows]

    if links := await legacy("link"):
        await connection.execute(
            insert(AgendaLinkRow).prefix_with("OR REPLACE"),
            [
                {
                    "link_key": key,
                    "publication_id": loads(payload).publication_id,
                    "payload": payload,
                }
                for key, payload in links
            ],
        )
    if fragments := await legacy("fragment"):
        await connection.execute(
            insert(AgendaFragmentRow).prefix_with("OR REPLACE"),
            [
                {
                    "fragment_key": key,
                    "published_at": loads(payload).published_at,
                    "payload": payload,
                }
                for key, payload in fragments
            ],
        )
    # Write only when there is something to move: the caller switches the
    # journal to WAL afterwards, which SQLite refuses inside a write transaction.
    if links or fragments:
        await connection.execute(
            delete(AgendaJsonRow).where(AgendaJsonRow.kind.in_(("link", "fragment")))
        )


async def drop_unused_search_index(connection: AsyncConnection) -> None:
    """Drop agenda_fts: search runs over the snapshot, and nothing read this FTS copy."""
    exists = await connection.scalar(text("SELECT 1 FROM sqlite_master WHERE name = 'agenda_fts'"))
    if exists:
        await connection.exec_driver_sql("DROP TABLE agenda_fts")


class SqliteAgendaStore:
    def __init__(self, session: async_sessionmaker) -> None:
        self._session = session
        self._write_lock = asyncio.Lock()
        self._published_cache: Snapshot | None = None

    def _row_to_pub(self, row: AgendaPublicationRow) -> PublicationVersion:
        return PublicationVersion(
            publication_id=row.publication_id,
            source_id=row.source_id,
            external_id=row.external_id,
            text=row.text,
            text_hash=row.text_hash,
            published_at=row.published_at,
            detected_at=row.detected_at,
            channel_ref=row.channel_ref,
            link=row.link,
            version=row.version,
        )

    async def record_publication(self, version: PublicationVersion) -> PublicationVersion | None:
        async with self._session() as session, session.begin():
            existing = await session.get(AgendaPublicationRow, version.publication_id)
            if existing is not None and existing.text_hash == version.text_hash:
                return self._row_to_pub(existing)
            previous = self._row_to_pub(existing) if existing is not None else None
            next_version = version.version
            if previous is not None and version.version <= previous.version:
                next_version = previous.version + 1
            if existing is None:
                session.add(
                    AgendaPublicationRow(
                        publication_id=version.publication_id,
                        source_id=version.source_id,
                        external_id=version.external_id,
                        text=version.text,
                        text_hash=version.text_hash,
                        published_at=version.published_at,
                        detected_at=version.detected_at,
                        channel_ref=version.channel_ref,
                        link=version.link,
                        version=next_version,
                    )
                )
            else:
                existing.text = version.text
                existing.text_hash = version.text_hash
                existing.published_at = version.published_at
                existing.detected_at = version.detected_at
                existing.channel_ref = version.channel_ref
                existing.link = version.link
                existing.version = next_version
            return previous

    async def publications_in(self, start: datetime, end: datetime) -> list[PublicationVersion]:
        async with self._session() as session:
            rows = (
                await session.scalars(
                    select(AgendaPublicationRow)
                    .where(
                        AgendaPublicationRow.published_at >= start,
                        AgendaPublicationRow.published_at < end,
                    )
                    .order_by(
                        AgendaPublicationRow.published_at,
                        AgendaPublicationRow.publication_id,
                    )
                )
            ).all()
            return [self._row_to_pub(row) for row in rows]

    async def _get_json(self, kind: str, item_id: str) -> Any | None:
        async with self._session() as session:
            row = await session.get(AgendaJsonRow, (kind, item_id))
            return None if row is None else loads(row.payload)

    async def _put_json(self, kind: str, item_id: str, value: Any) -> None:
        async with self._write_lock, self._session() as session, session.begin():
            row = await session.get(AgendaJsonRow, (kind, item_id))
            payload = dumps(value)
            if row is None:
                session.add(AgendaJsonRow(kind=kind, item_id=item_id, payload=payload))
            else:
                row.payload = payload

    async def _list_json(self, kind: str) -> list[Any]:
        async with self._session() as session:
            rows = (
                await session.scalars(select(AgendaJsonRow).where(AgendaJsonRow.kind == kind))
            ).all()
            return [loads(row.payload) for row in rows]

    async def get_extraction(self, reuse_key: str) -> ExtractionResult | None:
        return await self._get_json("extraction", reuse_key)

    async def save_extraction(self, result: ExtractionResult) -> None:
        await self._put_json("extraction", result.reuse_key, result)

    async def get_embedding(self, cache_key: str) -> list[float] | None:
        return await self._get_json("embedding", cache_key)

    async def save_embedding(self, cache_key: str, vector: list[float]) -> None:
        await self._put_json("embedding", cache_key, vector)

    async def enqueue(self, publication_id: str, reason: str) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(AgendaQueueRow, publication_id)
            if row is None:
                session.add(AgendaQueueRow(publication_id=publication_id, reason=reason))
            else:
                if reason.endswith("_error") and row.reason.split(":")[0] == reason:
                    count = int(row.reason.split(":")[1]) if ":" in row.reason else 1
                    reason = f"{reason}:{count + 1}"
                row.reason = reason

    async def mark_processed(self, publication_id: str) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(AgendaQueueRow, publication_id)
            if row is not None:
                await session.delete(row)

    async def expire_before(self, cutoff: datetime) -> None:
        async with self._session() as session, session.begin():
            rows = (
                await session.scalars(
                    select(AgendaQueueRow)
                    .join(
                        AgendaPublicationRow,
                        AgendaPublicationRow.publication_id == AgendaQueueRow.publication_id,
                    )
                    .where(
                        AgendaPublicationRow.published_at < cutoff,
                        AgendaQueueRow.reason != "expired",
                    )
                )
            ).all()
            for queued in rows:
                if queue_reason_retryable(queued.reason):
                    queued.reason = "expired"

    async def queue_depth(self) -> int:
        return len(await self.retryable_ids())

    async def queued_ids(self) -> list[str]:
        async with self._session() as session:
            rows = (await session.scalars(select(AgendaQueueRow))).all()
            return [row.publication_id for row in rows]

    async def retryable_ids(self) -> list[str]:
        async with self._session() as session:
            rows = (
                await session.scalars(
                    select(AgendaQueueRow).where(AgendaQueueRow.reason != "expired")
                )
            ).all()
            return [row.publication_id for row in rows if queue_reason_retryable(row.reason)]

    async def retryable_publications(self, end: datetime) -> list[PublicationVersion]:
        # Two steps so the small queue drives the lookup: a join lets SQLite
        # start from agenda_publication and range-scan the whole history.
        ids = sorted(await self.retryable_ids())
        pubs: list[PublicationVersion] = []
        async with self._session() as session:
            for offset in range(0, len(ids), _IN_CHUNK):
                rows = await session.scalars(
                    select(AgendaPublicationRow).where(
                        AgendaPublicationRow.publication_id.in_(ids[offset : offset + _IN_CHUNK]),
                        AgendaPublicationRow.published_at < end,
                    )
                )
                pubs.extend(self._row_to_pub(row) for row in rows)
        return sorted(pubs, key=lambda p: (p.published_at, p.publication_id))

    async def get_evidence_verdict(self, key: str) -> bool | None:
        return await self._get_json("evidence", key)

    async def save_evidence_verdict(self, key: str, supported: bool) -> None:
        await self._put_json("evidence", key, supported)

    async def save_entity(self, entity: Entity) -> None:
        await self._put_json("entity", entity.entity_id, entity)

    async def list_entities(self) -> list[Entity]:
        return await self._list_json("entity")

    async def save_story(self, story: Story) -> None:
        await self._put_json("story", story.story_id, story)

    async def list_stories(self) -> list[Story]:
        return await self._list_json("story")

    async def save_event(self, event: Event) -> None:
        await self._put_json("event", event.event_id, event)

    async def list_events(self) -> list[Event]:
        return await self._list_json("event")

    async def save_link(self, link: StoryLink) -> None:
        key = (
            f"{link.publication_id}:{link.version}:{link.fragment_index}:"
            f"{link.claim_index}:{link.story_id}"
        )
        async with self._write_lock, self._session() as session, session.begin():
            await session.merge(
                AgendaLinkRow(link_key=key, publication_id=link.publication_id, payload=dumps(link))
            )

    async def links_for_publications(self, publication_ids: set[str]) -> list[StoryLink]:
        # Ordered by key, as agenda_json returned them: candidate ties and the
        # story explanation quote depend on this order.
        ids = sorted(publication_ids)
        rows: list[tuple[str, str]] = []
        async with self._session() as session:
            for offset in range(0, len(ids), _IN_CHUNK):
                chunk = ids[offset : offset + _IN_CHUNK]
                query = select(AgendaLinkRow.link_key, AgendaLinkRow.payload)
                result = await session.execute(query.where(AgendaLinkRow.publication_id.in_(chunk)))
                rows.extend((key, payload) for key, payload in result)
        return [loads(payload) for _, payload in sorted(rows)]

    async def index_fragment(self, fragment: IndexedFragment) -> None:
        key = f"{fragment.publication_id}:{fragment.fragment_index}"
        async with self._write_lock, self._session() as session, session.begin():
            await session.merge(
                AgendaFragmentRow(
                    fragment_key=key, published_at=fragment.published_at, payload=dumps(fragment)
                )
            )

    async def fragments_since(self, start: datetime) -> list[IndexedFragment]:
        async with self._session() as session:
            payloads = await session.scalars(
                select(AgendaFragmentRow.payload)
                .where(AgendaFragmentRow.published_at >= start)
                .order_by(AgendaFragmentRow.fragment_key)
            )
            return [loads(payload) for payload in payloads]

    async def publish_snapshot(self, snapshot: Snapshot) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(AgendaSnapshotRow, snapshot.snapshot_id)
            payload = dumps(snapshot)
            if row is None:
                session.add(
                    AgendaSnapshotRow(
                        snapshot_id=snapshot.snapshot_id, published=True, payload=payload
                    )
                )
            else:
                if row.payload != payload:
                    raise ValueError("snapshot_id is immutable")
                row.published = True
            await session.execute(
                text("UPDATE agenda_snapshot SET published = false WHERE snapshot_id != :id"),
                {"id": snapshot.snapshot_id},
            )
            # Snapshot ids start with the UTC build time, so they sort in time order.
            oldest_kept = "snap-" + (snapshot.t - SNAPSHOT_RETENTION).strftime("%Y%m%dT%H%M%SZ")
            await session.execute(
                delete(AgendaSnapshotRow).where(
                    AgendaSnapshotRow.snapshot_id < oldest_kept,
                    AgendaSnapshotRow.published.is_(False),
                )
            )
        self._published_cache = snapshot

    async def get_snapshot(self, snapshot_id: str | None = None) -> Snapshot | None:
        async with self._session() as session:
            if snapshot_id is None:
                published_id = await session.scalar(
                    select(AgendaSnapshotRow.snapshot_id).where(
                        AgendaSnapshotRow.published.is_(True)
                    )
                )
                if published_id is None:
                    self._published_cache = None
                    return None
                if (
                    self._published_cache is not None
                    and self._published_cache.snapshot_id == published_id
                ):
                    return self._published_cache
                row = await session.get(AgendaSnapshotRow, published_id)
            else:
                if (
                    self._published_cache is not None
                    and self._published_cache.snapshot_id == snapshot_id
                ):
                    return self._published_cache
                row = await session.get(AgendaSnapshotRow, snapshot_id)
            snapshot = None if row is None else loads(row.payload)
            if snapshot_id is None:
                self._published_cache = snapshot
            return snapshot

    async def latest_nonempty_snapshot(self) -> Snapshot | None:
        # Payloads are megabytes each: list ids first, decode one at a time.
        async with self._session() as session:
            ids = (
                await session.scalars(
                    select(AgendaSnapshotRow.snapshot_id).order_by(
                        AgendaSnapshotRow.snapshot_id.desc()
                    )
                )
            ).all()
            for snapshot_id in ids:
                payload = await session.scalar(
                    select(AgendaSnapshotRow.payload).where(
                        AgendaSnapshotRow.snapshot_id == snapshot_id
                    )
                )
                if payload is not None and (snapshot := loads(payload)).agenda:
                    return snapshot
        return None

    async def set_cycle_state(self, state: CycleState) -> None:
        async with self._session() as session, session.begin():
            row = await session.get(AgendaCycleRow, 1)
            payload = dumps(state)
            if row is None:
                session.add(AgendaCycleRow(id=1, payload=payload))
            else:
                row.payload = payload

    async def get_cycle_state(self) -> CycleState:
        async with self._session() as session:
            row = await session.get(AgendaCycleRow, 1)
            return CycleState() if row is None else loads(row.payload)
