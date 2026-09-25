"""SQLite persistence for agenda publications, reuse caches, and snapshots."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Integer,
    bindparam,
    delete,
    exists,
    func,
    insert,
    literal_column,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from astrafeed.adapters.repository.sqlite.models import (
    AgendaCycleRow,
    AgendaEntityTokenRow,
    AgendaFragmentRow,
    AgendaJsonRow,
    AgendaLinkRow,
    AgendaPublicationRow,
    AgendaQueueRow,
    AgendaSnapshotRow,
    UtcDateTime,
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
    lexical_tokens,
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


async def migrate_agenda_entity_tokens(connection: AsyncConnection) -> None:
    """Backfill the searchable entity-name index in bounded keyset pages."""
    while True:
        missing = (
            select(AgendaJsonRow.item_id, AgendaJsonRow.payload)
            .where(
                AgendaJsonRow.kind == "entity",
                ~exists(
                    select(AgendaEntityTokenRow.entity_id).where(
                        AgendaEntityTokenRow.entity_id == AgendaJsonRow.item_id
                    )
                ),
            )
            .order_by(AgendaJsonRow.item_id)
            .limit(500)
        )
        rows = (await connection.execute(missing)).all()
        if not rows:
            return
        token_rows: list[dict[str, str]] = []
        for entity_id, payload in rows:
            entity = loads(payload)
            tokens = lexical_tokens(entity.canonical_name, *entity.aliases) or {""}
            token_rows.extend({"entity_id": entity_id, "token": token} for token in tokens)
        await connection.execute(insert(AgendaEntityTokenRow), token_rows)


def _retryable_clause():
    """SQL equivalent for the persisted ASCII retry counter format."""
    reason = AgendaQueueRow.reason
    prefix = func.rtrim(reason, "0123456789")
    numeric_tail = func.substr(reason, func.length(prefix) + 1)
    stopped_error = (
        (func.substr(prefix, -7) == "_error:")
        & (func.length(numeric_tail) > 0)
        & (func.cast(numeric_tail, Integer) >= 3)
    )
    return (reason != "expired") & ~stopped_error


_RETRYABLE_QUEUE_SQL = (
    "q.reason != 'expired' AND NOT ("
    "substr(rtrim(q.reason, '0123456789'), -7) = '_error:' "
    "AND length(q.reason) > length(rtrim(q.reason, '0123456789')) "
    "AND CAST(substr(q.reason, length(rtrim(q.reason, '0123456789')) + 1) "
    "AS INTEGER) >= 3)"
)


async def migrate_agenda_index_tables(connection: AsyncConnection) -> None:
    """Move links and fragments out of agenda_json into their indexed tables.

    Earlier releases stored them as untyped JSON rows, so every lookup read the
    whole history. Runs at startup; a no-op once agenda_json holds neither kind.
    """

    # Bound migration memory to a page; delete each page after its indexed
    # replacement has been written so a restart can safely resume.
    for kind, model, key_name, attribute in (
        ("link", AgendaLinkRow, "link_key", "publication_id"),
        ("fragment", AgendaFragmentRow, "fragment_key", "published_at"),
    ):
        while True:
            rows = (
                await connection.execute(
                    select(AgendaJsonRow.item_id, AgendaJsonRow.payload)
                    .where(AgendaJsonRow.kind == kind)
                    .order_by(AgendaJsonRow.item_id)
                    .limit(_IN_CHUNK)
                )
            ).all()
            if not rows:
                break
            await connection.execute(
                insert(model).prefix_with("OR REPLACE"),
                [
                    {
                        key_name: key,
                        attribute: getattr(loads(payload), attribute),
                        "payload": payload,
                    }
                    for key, payload in rows
                ],
            )
            await connection.execute(
                delete(AgendaJsonRow).where(
                    AgendaJsonRow.kind == kind,
                    AgendaJsonRow.item_id.in_([key for key, _ in rows]),
                )
            )
    # SQLAlchemy's checkfirst cannot reflect expression indexes on SQLite;
    # create this one here so existing and fresh databases use the same path.
    await connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_agenda_json_event_story "
        "ON agenda_json (json_extract(payload, '$.story_id')) WHERE kind = 'event'"
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

    async def _list_json_ids(self, kind: str, item_ids: set[str]) -> list[Any]:
        if not item_ids:
            return []
        values: list[tuple[str, str]] = []
        ids = sorted(item_ids)
        async with self._session() as session:
            for offset in range(0, len(ids), _IN_CHUNK):
                result = await session.execute(
                    select(AgendaJsonRow.item_id, AgendaJsonRow.payload).where(
                        AgendaJsonRow.kind == kind,
                        AgendaJsonRow.item_id.in_(ids[offset : offset + _IN_CHUNK]),
                    )
                )
                values.extend(result)
        return [loads(payload) for _, payload in sorted(values)]

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
            await session.execute(
                update(AgendaQueueRow)
                .where(
                    AgendaQueueRow.publication_id.in_(
                        select(AgendaPublicationRow.publication_id).where(
                            AgendaPublicationRow.published_at < cutoff
                        )
                    ),
                    _retryable_clause(),
                )
                .values(reason="expired")
            )

    async def queue_depth(self) -> int:
        async with self._session() as session:
            return int(
                await session.scalar(
                    select(func.count()).select_from(AgendaQueueRow).where(_retryable_clause())
                )
                or 0
            )

    async def queue_stopped(self) -> int:
        async with self._session() as session:
            return int(
                await session.scalar(
                    select(func.count()).select_from(AgendaQueueRow).where(~_retryable_clause())
                )
                or 0
            )

    async def queued_ids(self, publication_ids: set[str] | None = None) -> list[str]:
        if publication_ids is not None and not publication_ids:
            return []
        async with self._session() as session:
            if publication_ids is None:
                return list(await session.scalars(select(AgendaQueueRow.publication_id)))
            ids = sorted(publication_ids)
            found: list[str] = []
            for offset in range(0, len(ids), _IN_CHUNK):
                found.extend(
                    await session.scalars(
                        select(AgendaQueueRow.publication_id).where(
                            AgendaQueueRow.publication_id.in_(ids[offset : offset + _IN_CHUNK])
                        )
                    )
                )
            return found

    async def retryable_ids(self) -> list[str]:
        async with self._session() as session:
            return list(
                await session.scalars(
                    select(AgendaQueueRow.publication_id).where(_retryable_clause())
                )
            )

    async def retryable_publications(
        self,
        end: datetime,
        *,
        source_ids: set[int] | None = None,
        limit: int | None = None,
        current_start: datetime | None = None,
        previous_start: datetime | None = None,
    ) -> list[PublicationVersion]:
        if source_ids is not None and not source_ids:
            return []
        where = f"q.publication_id = p.publication_id AND {_RETRYABLE_QUEUE_SQL} "
        where += "AND p.published_at < :end"
        params: dict[str, Any] = {"end": end}
        if source_ids is not None:
            where += " AND p.source_id IN :source_ids"
            params["source_ids"] = sorted(source_ids)
        if current_start is not None and previous_start is not None:
            order = (
                "CASE WHEN p.published_at >= :current_start THEN 0 "
                "WHEN p.published_at >= :previous_start THEN 1 ELSE 2 END, "
                "p.published_at, p.publication_id"
            )
            params.update(current_start=current_start, previous_start=previous_start)
        else:
            order = "p.published_at, p.publication_id"
        sql = (
            "SELECT p.* FROM agenda_queue AS q CROSS JOIN agenda_publication AS p "
            f"WHERE {where} ORDER BY {order}"
        )
        if limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = limit
        statement = text(sql)
        statement = statement.bindparams(bindparam("end", type_=UtcDateTime()))
        if source_ids is not None:
            statement = statement.bindparams(bindparam("source_ids", expanding=True))
        if current_start is not None and previous_start is not None:
            statement = statement.bindparams(
                bindparam("current_start", type_=UtcDateTime()),
                bindparam("previous_start", type_=UtcDateTime()),
            )
        query = select(AgendaPublicationRow).from_statement(statement)
        async with self._session() as session:
            return [self._row_to_pub(row) for row in await session.scalars(query, params)]

    async def retryable_publication_count(self, end: datetime, source_ids: set[int]) -> int:
        if not source_ids:
            return 0
        statement = text(
            "SELECT count(*) FROM agenda_queue AS q CROSS JOIN agenda_publication AS p "
            f"WHERE q.publication_id = p.publication_id AND {_RETRYABLE_QUEUE_SQL} "
            "AND p.published_at < :end AND p.source_id IN :source_ids"
        ).bindparams(bindparam("source_ids", expanding=True), bindparam("end", type_=UtcDateTime()))
        async with self._session() as session:
            return int(
                await session.scalar(statement, {"end": end, "source_ids": sorted(source_ids)}) or 0
            )

    async def get_evidence_verdict(self, key: str) -> bool | None:
        return await self._get_json("evidence", key)

    async def save_evidence_verdict(self, key: str, supported: bool) -> None:
        await self._put_json("evidence", key, supported)

    async def save_entity(self, entity: Entity) -> None:
        async with self._write_lock, self._session() as session, session.begin():
            row = await session.get(AgendaJsonRow, ("entity", entity.entity_id))
            payload = dumps(entity)
            if row is None:
                session.add(AgendaJsonRow(kind="entity", item_id=entity.entity_id, payload=payload))
            else:
                row.payload = payload
            await session.execute(
                delete(AgendaEntityTokenRow).where(
                    AgendaEntityTokenRow.entity_id == entity.entity_id
                )
            )
            tokens = lexical_tokens(entity.canonical_name, *entity.aliases) or {""}
            session.add_all(
                AgendaEntityTokenRow(entity_id=entity.entity_id, token=token) for token in tokens
            )

    async def list_entities(
        self, predicate: Callable[[Entity], bool] | None = None
    ) -> list[Entity]:
        if predicate is None:
            return await self._list_json("entity")
        selected: list[Entity] = []
        async with self._session() as session:
            rows = await session.stream_scalars(
                select(AgendaJsonRow.payload).where(AgendaJsonRow.kind == "entity")
            )
            async for payload in rows:
                entity = loads(payload)
                if predicate(entity):
                    selected.append(entity)
        return selected

    async def entities_matching(
        self,
        entity_ids: set[str],
        terms: set[str],
        predicate: Callable[[Entity], bool] | None = None,
    ) -> list[Entity]:
        normalized = sorted(term.casefold() for term in terms if term)
        candidate_ids = set(entity_ids)
        async with self._session() as session:
            for offset in range(0, len(normalized), _IN_CHUNK):
                chunk = normalized[offset : offset + _IN_CHUNK]
                if chunk:
                    candidate_ids.update(
                        await session.scalars(
                            select(AgendaEntityTokenRow.entity_id).where(
                                AgendaEntityTokenRow.token.in_(chunk)
                            )
                        )
                    )
        entities = await self._list_json_ids("entity", candidate_ids)
        return [entity for entity in entities if predicate is None or predicate(entity)]

    async def entity_count(self) -> int:
        async with self._session() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(AgendaJsonRow)
                    .where(AgendaJsonRow.kind == "entity")
                )
                or 0
            )

    async def save_story(self, story: Story) -> None:
        await self._put_json("story", story.story_id, story)

    async def get_story(self, story_id: str) -> Story | None:
        return await self._get_json("story", story_id)

    async def list_stories(self, story_ids: set[str] | None = None) -> list[Story]:
        return (
            await self._list_json("story")
            if story_ids is None
            else await self._list_json_ids("story", story_ids)
        )

    async def save_event(self, event: Event) -> None:
        await self._put_json("event", event.event_id, event)

    async def list_events(
        self, event_ids: set[str] | None = None, *, story_ids: set[str] | None = None
    ) -> list[Event]:
        if event_ids is not None:
            events = await self._list_json_ids("event", event_ids)
            return [event for event in events if story_ids is None or event.story_id in story_ids]
        if story_ids is None:
            return await self._list_json("event")
        if not story_ids:
            return []
        selected: list[tuple[str, str]] = []
        ids = sorted(story_ids)
        async with self._session() as session:
            for offset in range(0, len(ids), _IN_CHUNK):
                rows = await session.execute(
                    select(AgendaJsonRow.item_id, AgendaJsonRow.payload).where(
                        text("agenda_json.kind = 'event'"),
                        literal_column("json_extract(agenda_json.payload, '$.story_id')").in_(
                            ids[offset : offset + _IN_CHUNK]
                        ),
                    )
                )
                selected.extend(rows)
        return [loads(payload) for _, payload in sorted(selected)]

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

    async def save_assignment(
        self,
        entities: tuple[Entity, ...],
        story: Story,
        event: Event | None,
        links: tuple[StoryLink, ...],
        fragment: IndexedFragment,
    ) -> None:
        """Commit one fragment's catalog and evidence in a single transaction."""
        async with self._write_lock, self._session() as session, session.begin():
            catalog = [
                {"kind": "entity", "item_id": entity.entity_id, "payload": dumps(entity)}
                for entity in entities
            ]
            catalog.append({"kind": "story", "item_id": story.story_id, "payload": dumps(story)})
            if event is not None:
                catalog.append(
                    {"kind": "event", "item_id": event.event_id, "payload": dumps(event)}
                )
            await session.execute(insert(AgendaJsonRow).prefix_with("OR REPLACE"), catalog)
            if links:
                await session.execute(
                    insert(AgendaLinkRow).prefix_with("OR REPLACE"),
                    [
                        {
                            "link_key": (
                                f"{link.publication_id}:{link.version}:{link.fragment_index}:"
                                f"{link.claim_index}:{link.story_id}"
                            ),
                            "publication_id": link.publication_id,
                            "payload": dumps(link),
                        }
                        for link in links
                    ],
                )
            await session.execute(
                insert(AgendaFragmentRow).prefix_with("OR REPLACE"),
                {
                    "fragment_key": f"{fragment.publication_id}:{fragment.fragment_index}",
                    "published_at": fragment.published_at,
                    "payload": dumps(fragment),
                },
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
                text(
                    "UPDATE agenda_snapshot SET published = false "
                    "WHERE published = true AND snapshot_id != :id"
                ),
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

    async def published_snapshot_meta(self) -> tuple[str, datetime, datetime] | None:
        async with self._session() as session:
            row = (
                await session.execute(
                    select(
                        AgendaSnapshotRow.snapshot_id,
                        func.json_extract(AgendaSnapshotRow.payload, "$.t.v"),
                        func.json_extract(AgendaSnapshotRow.payload, "$.published_at.v"),
                    ).where(AgendaSnapshotRow.published.is_(True))
                )
            ).first()
            if row is None:
                return None
            return row[0], datetime.fromisoformat(row[1]), datetime.fromisoformat(row[2])

    async def latest_nonempty_snapshot(self) -> Snapshot | None:
        # Decode one candidate at a time; older snapshots are retained only
        # until the publish retention window closes.
        async with self._session() as session:
            payloads = await session.stream_scalars(
                select(AgendaSnapshotRow.payload).order_by(AgendaSnapshotRow.snapshot_id.desc())
            )
            async for payload in payloads:
                if (snapshot := loads(payload)).agenda:
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
