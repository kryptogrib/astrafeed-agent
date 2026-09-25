from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol

from astrafeed.domain.agenda import (
    CycleState,
    DiscussionDigest,
    Entity,
    Event,
    ExtractionResult,
    IndexedFragment,
    PublicationVersion,
    Snapshot,
    Story,
    StoryLink,
)
from astrafeed.domain.models import DiscussionComment, Item


class OpenExtractor(Protocol):
    async def extract(self, text: str) -> ExtractionResult: ...


class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class StoryAssigner(Protocol):
    async def assign(
        self,
        *,
        fragment: IndexedFragment,
        entities: Sequence[Entity],
        stories: Sequence[Story],
        events: Sequence[Event],
        candidates: Sequence[IndexedFragment],
    ) -> AssignmentDraft: ...


class AssignmentDraft(Protocol):
    """Structural result of story assignment; concrete type lives in adapters."""


class EvidenceVerifier(Protocol):
    async def verify(self, story: Story, quotes: Sequence[str]) -> list[bool]: ...


class CommentReader(Protocol):
    async def reply_counts(self, channel_ref: str, post_ids: Sequence[str]) -> dict[str, int]: ...

    async def fetch_comments(self, item: Item, *, limit: int) -> list[DiscussionComment]: ...


class DiscussionSummarizer(Protocol):
    async def summarize(
        self, title: str, posts: Sequence[str], comments: Sequence[str]
    ) -> DiscussionDigest: ...


class Translator(Protocol):
    async def to_english(self, texts: Sequence[str]) -> list[str]: ...


class AgendaStore(Protocol):
    async def record_publication(
        self, version: PublicationVersion
    ) -> PublicationVersion | None: ...

    async def publications_in(self, start: datetime, end: datetime) -> list[PublicationVersion]: ...

    async def get_extraction(self, reuse_key: str) -> ExtractionResult | None: ...

    async def save_extraction(self, result: ExtractionResult) -> None: ...

    async def get_embedding(self, cache_key: str) -> list[float] | None: ...

    async def save_embedding(self, cache_key: str, vector: list[float]) -> None: ...

    async def enqueue(self, publication_id: str, reason: str) -> None: ...

    async def mark_processed(self, publication_id: str) -> None: ...

    async def expire_before(self, cutoff: datetime) -> None: ...

    async def queue_depth(self) -> int: ...

    async def queue_stopped(self) -> int: ...

    async def queued_ids(self, publication_ids: set[str] | None = None) -> list[str]: ...

    async def retryable_ids(self) -> list[str]: ...

    async def retryable_publications(
        self,
        end: datetime,
        *,
        source_ids: set[int] | None = None,
        limit: int | None = None,
        current_start: datetime | None = None,
        previous_start: datetime | None = None,
    ) -> list[PublicationVersion]:
        """Latest versions of retryable queued posts published before ``end``."""
        ...

    async def retryable_publication_count(self, end: datetime, source_ids: set[int]) -> int: ...

    async def get_evidence_verdict(self, key: str) -> bool | None: ...

    async def save_evidence_verdict(self, key: str, supported: bool) -> None: ...

    async def save_entity(self, entity: Entity) -> None: ...

    async def list_entities(
        self, predicate: Callable[[Entity], bool] | None = None
    ) -> list[Entity]: ...

    async def entities_matching(
        self,
        entity_ids: set[str],
        terms: set[str],
        predicate: Callable[[Entity], bool] | None = None,
    ) -> list[Entity]: ...

    async def entity_count(self) -> int: ...

    async def save_story(self, story: Story) -> None: ...

    async def get_story(self, story_id: str) -> Story | None: ...

    async def list_stories(self, story_ids: set[str] | None = None) -> list[Story]: ...

    async def save_event(self, event: Event) -> None: ...

    async def list_events(
        self, event_ids: set[str] | None = None, *, story_ids: set[str] | None = None
    ) -> list[Event]: ...

    async def save_link(self, link: StoryLink) -> None: ...

    async def links_for_publications(self, publication_ids: set[str]) -> list[StoryLink]: ...

    async def index_fragment(self, fragment: IndexedFragment) -> None: ...

    async def save_assignment(
        self,
        entities: tuple[Entity, ...],
        story: Story,
        event: Event | None,
        links: tuple[StoryLink, ...],
        fragment: IndexedFragment,
    ) -> None: ...

    async def fragments_since(self, start: datetime) -> list[IndexedFragment]: ...

    async def publish_snapshot(self, snapshot: Snapshot) -> None: ...

    async def get_snapshot(self, snapshot_id: str | None = None) -> Snapshot | None: ...

    async def published_snapshot_meta(self) -> tuple[str, datetime, datetime] | None: ...

    async def latest_nonempty_snapshot(self) -> Snapshot | None: ...

    async def set_cycle_state(self, state: CycleState) -> None: ...

    async def get_cycle_state(self) -> CycleState: ...
