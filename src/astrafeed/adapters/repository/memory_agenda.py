from __future__ import annotations

from datetime import datetime

from astrafeed.domain.agenda import (
    CycleState,
    Entity,
    Event,
    ExtractionResult,
    IndexedFragment,
    PublicationVersion,
    Snapshot,
    Story,
    StoryLink,
)


class InMemoryAgendaStore:
    def __init__(self) -> None:
        self._versions: dict[str, list[PublicationVersion]] = {}
        self._extractions: dict[str, ExtractionResult] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._queue: dict[str, str] = {}
        self._entities: dict[str, Entity] = {}
        self._stories: dict[str, Story] = {}
        self._events: dict[str, Event] = {}
        self._links: list[StoryLink] = []
        self._fragments: list[IndexedFragment] = []
        self._snapshots: dict[str, Snapshot] = {}
        self._published_id: str | None = None
        self._cycle = CycleState()

    def locations_for_hash(self, digest: str) -> list[PublicationVersion]:
        found: list[PublicationVersion] = []
        for versions in self._versions.values():
            latest = versions[-1]
            if latest.text_hash == digest:
                found.append(latest)
        return found

    def queue_reason(self, publication_id: str) -> str | None:
        return self._queue.get(publication_id)

    def latest_version(self, publication_id: str) -> PublicationVersion:
        return self._versions[publication_id][-1]

    async def record_publication(self, version: PublicationVersion) -> PublicationVersion | None:
        history = self._versions.setdefault(version.publication_id, [])
        previous = history[-1] if history else None
        if previous is not None and previous.text_hash == version.text_hash:
            return previous
        next_version = version
        if previous is not None and version.version <= previous.version:
            next_version = PublicationVersion(
                publication_id=version.publication_id,
                source_id=version.source_id,
                external_id=version.external_id,
                text=version.text,
                text_hash=version.text_hash,
                published_at=version.published_at,
                detected_at=version.detected_at,
                channel_ref=version.channel_ref,
                link=version.link,
                version=previous.version + 1,
            )
        history.append(next_version)
        return previous

    async def latest_publication(self, publication_id: str) -> PublicationVersion | None:
        history = self._versions.get(publication_id)
        return history[-1] if history else None

    async def publications_in(self, start: datetime, end: datetime) -> list[PublicationVersion]:
        latest = [versions[-1] for versions in self._versions.values()]
        in_range = [p for p in latest if start <= p.published_at < end]
        return sorted(in_range, key=lambda p: (p.published_at, p.publication_id))

    async def get_extraction(self, reuse_key: str) -> ExtractionResult | None:
        return self._extractions.get(reuse_key)

    async def save_extraction(self, result: ExtractionResult) -> None:
        self._extractions[result.reuse_key] = result

    async def get_embedding(self, cache_key: str) -> list[float] | None:
        return self._embeddings.get(cache_key)

    async def save_embedding(self, cache_key: str, vector: list[float]) -> None:
        self._embeddings[cache_key] = vector

    async def enqueue(self, publication_id: str, reason: str) -> None:
        self._queue[publication_id] = reason

    async def mark_processed(self, publication_id: str) -> None:
        self._queue.pop(publication_id, None)

    async def queue_depth(self) -> int:
        return len(self._queue)

    async def queued_ids(self) -> list[str]:
        return list(self._queue)

    async def save_entity(self, entity: Entity) -> None:
        self._entities[entity.entity_id] = entity

    async def list_entities(self) -> list[Entity]:
        return list(self._entities.values())

    async def save_story(self, story: Story) -> None:
        self._stories[story.story_id] = story

    async def list_stories(self) -> list[Story]:
        return list(self._stories.values())

    async def save_event(self, event: Event) -> None:
        self._events[event.event_id] = event

    async def list_events(self) -> list[Event]:
        return list(self._events.values())

    async def save_link(self, link: StoryLink) -> None:
        key = (
            link.publication_id,
            link.version,
            link.fragment_index,
            link.claim_index,
            link.story_id,
        )
        if any(
            (
                existing.publication_id,
                existing.version,
                existing.fragment_index,
                existing.claim_index,
                existing.story_id,
            )
            == key
            for existing in self._links
        ):
            return
        self._links.append(link)

    async def links_for_publications(self, publication_ids: set[str]) -> list[StoryLink]:
        return [link for link in self._links if link.publication_id in publication_ids]

    async def index_fragment(self, fragment: IndexedFragment) -> None:
        self._fragments.append(fragment)

    async def fragments_since(self, start: datetime) -> list[IndexedFragment]:
        return [f for f in self._fragments if f.published_at >= start]

    async def publish_snapshot(self, snapshot: Snapshot) -> None:
        self._snapshots[snapshot.snapshot_id] = snapshot
        self._published_id = snapshot.snapshot_id

    async def get_snapshot(self, snapshot_id: str | None = None) -> Snapshot | None:
        if snapshot_id is None:
            if self._published_id is None:
                return None
            return self._snapshots[self._published_id]
        return self._snapshots.get(snapshot_id)

    async def set_cycle_state(self, state: CycleState) -> None:
        self._cycle = state

    async def get_cycle_state(self) -> CycleState:
        return self._cycle
