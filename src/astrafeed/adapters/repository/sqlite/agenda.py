"""SQLite persistence for agenda publications, reuse caches, and snapshots."""

from __future__ import annotations

import asyncio
import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from astrafeed.adapters.repository.sqlite.models import (
    AgendaCycleRow,
    AgendaJsonRow,
    AgendaPublicationRow,
    AgendaQueueRow,
    AgendaSnapshotRow,
)
from astrafeed.domain.agenda import (
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


class SqliteAgendaStore:
    def __init__(self, session: async_sessionmaker) -> None:
        self._session = session
        self._write_lock = asyncio.Lock()
        self._published_cache: Snapshot | None = None

    async def ensure_search(self) -> None:
        async with self._session() as session:
            await session.execute(
                text(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS agenda_fts USING fts5("
                    "snapshot_id UNINDEXED, story_id UNINDEXED, kind, body)"
                )
            )
            await session.commit()

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

    async def latest_publication(self, publication_id: str) -> PublicationVersion | None:
        async with self._session() as session:
            row = await session.get(AgendaPublicationRow, publication_id)
            return self._row_to_pub(row) if row is not None else None

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

    async def queue_depth(self) -> int:
        return len(await self.queued_ids())

    async def queued_ids(self) -> list[str]:
        async with self._session() as session:
            rows = (await session.scalars(select(AgendaQueueRow))).all()
            return [row.publication_id for row in rows]

    async def retryable_ids(self) -> list[str]:
        async with self._session() as session:
            rows = (await session.scalars(select(AgendaQueueRow))).all()
            return [row.publication_id for row in rows if queue_reason_retryable(row.reason)]

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
        await self._put_json("link", key, link)

    async def links_for_publications(self, publication_ids: set[str]) -> list[StoryLink]:
        links = await self._list_json("link")
        return [link for link in links if link.publication_id in publication_ids]

    async def index_fragment(self, fragment: IndexedFragment) -> None:
        key = f"{fragment.publication_id}:{fragment.fragment_index}"
        await self._put_json("fragment", key, fragment)

    async def fragments_since(self, start: datetime) -> list[IndexedFragment]:
        fragments = await self._list_json("fragment")
        return [fragment for fragment in fragments if fragment.published_at >= start]

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
            others = (
                await session.scalars(
                    select(AgendaSnapshotRow).where(
                        AgendaSnapshotRow.snapshot_id != snapshot.snapshot_id
                    )
                )
            ).all()
            for other in others:
                other.published = False
        await self.ensure_search()
        async with self._session() as session, session.begin():
            await session.execute(
                text("DELETE FROM agenda_fts WHERE snapshot_id = :sid"),
                {"sid": snapshot.snapshot_id},
            )
            for doc in snapshot.search_docs:
                await session.execute(
                    text(
                        "INSERT INTO agenda_fts(snapshot_id, story_id, kind, body) "
                        "VALUES (:sid, :story, :kind, :body)"
                    ),
                    {
                        "sid": snapshot.snapshot_id,
                        "story": doc.story_id,
                        "kind": doc.kind,
                        "body": doc.text,
                    },
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
        async with self._session() as session:
            rows = (
                await session.scalars(
                    select(AgendaSnapshotRow).order_by(AgendaSnapshotRow.snapshot_id.desc())
                )
            ).all()
            for row in rows:
                snapshot = loads(row.payload)
                if snapshot.agenda:
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
