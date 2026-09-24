"""Embed fragments, collect candidates, and apply story assignment."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from astrafeed.domain.agenda import (
    CANDIDATE_K,
    LOOKBACK,
    Claim,
    Entity,
    Event,
    ExtractionResult,
    Fragment,
    IndexedFragment,
    PublicationVersion,
    Story,
    StoryLink,
    cosine_similarity,
    embedding_cache_key,
    embedding_input,
    lexical_tokens,
)
from astrafeed.domain.spend_budget import BudgetExceeded
from astrafeed.ports.agenda import AgendaStore, Embedder, StoryAssigner

_log = logging.getLogger(__name__)


def _stable_id(prefix: str, *parts: str) -> str:
    raw = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{raw}"


def find_candidates(
    query: IndexedFragment, pool: Sequence[IndexedFragment]
) -> list[IndexedFragment]:
    others = [
        item
        for item in pool
        if not (
            item.publication_id == query.publication_id
            and item.fragment_index == query.fragment_index
        )
    ]
    semantic = sorted(
        [item for item in others if item.vector and query.vector],
        key=lambda item: cosine_similarity(query.vector or [], item.vector or []),
        reverse=True,
    )[:CANDIDATE_K]
    query_tokens = lexical_tokens(query.text, query.claim_text, *query.entity_surfaces)

    def lex_score(item: IndexedFragment) -> int:
        return len(query_tokens & lexical_tokens(item.text, item.claim_text, *item.entity_surfaces))

    lexical = sorted(
        [item for item in others if lex_score(item) > 0],
        key=lex_score,
        reverse=True,
    )[:CANDIDATE_K]
    seen: set[tuple[str, int]] = set()
    merged: list[IndexedFragment] = []
    for item in [*semantic, *lexical]:
        key = (item.publication_id, item.fragment_index)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _claim_text(fragment: Fragment) -> str:
    return " ".join(claim.quote for claim in fragment.claims)


def select_assignment_context(
    fragment: IndexedFragment,
    candidates: Sequence[IndexedFragment],
    links: Sequence[StoryLink],
    entities: Sequence[Entity],
    stories: Sequence[Story],
    events: Sequence[Event],
) -> tuple[list[Entity], list[Story], list[Event]]:
    candidate_keys = {(item.publication_id, item.fragment_index) for item in candidates}
    matched_links = [
        link for link in links if (link.publication_id, link.fragment_index) in candidate_keys
    ]
    story_ids = {link.story_id for link in matched_links}
    event_ids = {link.event_id for link in matched_links if link.event_id}
    entity_ids = {entity_id for link in matched_links for entity_id in link.entity_ids}
    surfaces = {
        surface.casefold()
        for surface in (
            *fragment.entity_surfaces,
            *(surface for item in candidates for surface in item.entity_surfaces),
        )
    }
    selected_entities = sorted(
        (
            entity
            for entity in entities
            if entity.entity_id in entity_ids
            or entity.canonical_name.casefold() in surfaces
            or any(alias.casefold() in surfaces for alias in entity.aliases)
        ),
        key=lambda entity: entity.entity_id,
    )
    selected_stories = sorted(
        (story for story in stories if story.story_id in story_ids),
        key=lambda story: story.story_id,
    )
    selected_events = sorted(
        (event for event in events if event.event_id in event_ids),
        key=lambda event: event.event_id,
    )
    return selected_entities, selected_stories, selected_events


async def _vector_for(store: AgendaStore, embedder: Embedder, text: str) -> list[float]:
    key = embedding_cache_key(text)
    cached = await store.get_embedding(key)
    if cached is not None:
        return cached
    vectors = await embedder.embed([text])
    vector = list(vectors[0])
    await store.save_embedding(key, vector)
    return vector


def _apply_entities(existing: list[Entity], assignment) -> list[Entity]:
    by_id = {entity.entity_id: entity for entity in existing}
    chosen: list[Entity] = []
    for surface, decision, entity_id, canonical in assignment.entity_decisions:
        name = canonical or surface
        if decision == "existing" and entity_id and entity_id in by_id:
            chosen.append(by_id[entity_id])
            continue
        new_id = entity_id or _stable_id("en", name.casefold())
        status: Literal["confirmed", "ambiguous"] = (
            "ambiguous" if decision == "ambiguous" else "confirmed"
        )
        entity = Entity(entity_id=new_id, canonical_name=name, status=status, aliases=(surface,))
        by_id[new_id] = entity
        chosen.append(entity)
    return chosen


@dataclass(frozen=True)
class AssignmentContext:
    candidates: tuple[IndexedFragment, ...]
    entities: tuple[Entity, ...]
    stories: tuple[Story, ...]
    events: tuple[Event, ...]


@dataclass(frozen=True)
class PreparedFragment:
    index: int
    fragment: Fragment
    indexed: IndexedFragment
    context: AssignmentContext
    assignment: object | None


@dataclass(frozen=True)
class AssignmentEffect:
    entities: tuple[Entity, ...]
    story: Story | None
    event: Event | None
    links: tuple[StoryLink, ...]
    indexed: IndexedFragment | None
    valid: bool = True


def _context_from_state(
    indexed: IndexedFragment,
    pool: Sequence[IndexedFragment],
    links: Sequence[StoryLink],
    entities: Sequence[Entity],
    stories: Sequence[Story],
    events: Sequence[Event],
) -> AssignmentContext:
    earlier = [
        item
        for item in pool
        if indexed.published_at - LOOKBACK <= item.published_at < indexed.published_at
    ]
    candidates = find_candidates(indexed, earlier)
    selected_entities, selected_stories, selected_events = select_assignment_context(
        indexed, candidates, links, entities, stories, events
    )
    return AssignmentContext(
        tuple(candidates),
        tuple(selected_entities),
        tuple(selected_stories),
        tuple(selected_events),
    )


async def _context_from_store(store: AgendaStore, indexed: IndexedFragment) -> AssignmentContext:
    pool = await store.fragments_since(indexed.published_at - LOOKBACK)
    candidates = find_candidates(
        indexed, [item for item in pool if item.published_at < indexed.published_at]
    )
    links = await store.links_for_publications({item.publication_id for item in candidates})
    selected_entities, selected_stories, selected_events = select_assignment_context(
        indexed,
        candidates,
        links,
        await store.list_entities(),
        await store.list_stories(),
        await store.list_events(),
    )
    return AssignmentContext(
        tuple(candidates),
        tuple(selected_entities),
        tuple(selected_stories),
        tuple(selected_events),
    )


async def _indexed_for(
    store: AgendaStore,
    embedder: Embedder,
    publication: PublicationVersion,
    index: int,
    fragment: Fragment,
) -> IndexedFragment:
    surfaces = [entity.surface for entity in fragment.entities]
    text = embedding_input(fragment.text, surfaces)
    try:
        vector = await _vector_for(store, embedder, text)
    except BudgetExceeded:
        raise
    except Exception:
        await store.enqueue(publication.publication_id, "embed_error")
        raise
    return IndexedFragment(
        publication_id=publication.publication_id,
        published_at=publication.published_at,
        fragment_index=index,
        text=fragment.text,
        entity_surfaces=tuple(surfaces),
        claim_text=_claim_text(fragment),
        vector=vector,
    )


async def _decide(assigner: StoryAssigner, indexed: IndexedFragment, context: AssignmentContext):
    return await assigner.assign(
        fragment=indexed,
        entities=context.entities,
        stories=context.stories,
        events=context.events,
        candidates=context.candidates,
    )


async def _apply_decision(
    store: AgendaStore,
    publication: PublicationVersion,
    index: int,
    fragment: Fragment,
    indexed: IndexedFragment,
    context: AssignmentContext,
    assignment: object,
) -> AssignmentEffect:
    story = _resolve_story(assignment, list(context.stories), publication)
    if story is None:
        if getattr(assignment, "story_decision", None) != "ambiguous":
            await store.enqueue(publication.publication_id, "assign_error")
            return AssignmentEffect((), None, None, (), None, valid=False)
        return AssignmentEffect((), None, None, (), None)
    chosen_entities = _apply_entities(list(context.entities), assignment)
    for entity in chosen_entities:
        await store.save_entity(entity)
    await store.save_story(story)
    event_id = _resolve_event(assignment, story.story_id, list(context.events))
    event = None
    if event_id:
        event = Event(
            event_id=event_id,
            story_id=story.story_id,
            when=getattr(assignment, "event_when", ""),
            amount=getattr(assignment, "event_amount", ""),
        )
        await store.save_event(event)
    new_links = tuple(
        _link(
            story.story_id,
            publication,
            index,
            claim_index,
            claim,
            chosen_entities,
            event_id,
            getattr(assignment, "paraphrase_ru", ""),
        )
        for claim_index, claim in enumerate(fragment.claims)
    )
    for link in new_links:
        await store.save_link(link)
    await store.index_fragment(indexed)
    return AssignmentEffect(tuple(chosen_entities), story, event, new_links, indexed)


async def assign_publication(
    store: AgendaStore,
    embedder: Embedder,
    assigner: StoryAssigner,
    publication: PublicationVersion,
    extraction: ExtractionResult,
) -> None:
    if extraction.status != "ok":
        return
    for index, fragment in enumerate(extraction.fragments):
        if not fragment.claims:
            continue
        indexed = await _indexed_for(store, embedder, publication, index, fragment)
        context = await _context_from_store(store, indexed)
        try:
            assignment = await _decide(assigner, indexed, context)
        except BudgetExceeded:
            raise
        except Exception:
            await store.enqueue(publication.publication_id, "assign_error")
            return
        effect = await _apply_decision(
            store, publication, index, fragment, indexed, context, assignment
        )
        if not effect.valid:
            return
    await store.mark_processed(publication.publication_id)


async def assign_speculative_batch(
    store: AgendaStore,
    embedder: Embedder,
    assigner: StoryAssigner,
    jobs: Sequence[tuple[PublicationVersion, ExtractionResult]],
    *,
    concurrency: int = 16,
) -> tuple[int, int]:
    """Overlap independent model calls, then validate and commit in time order.

    A proposal is reused only when its complete candidate context still equals
    the context a sequential assignment would see at commit time.
    """
    if not jobs:
        return 0, 0
    if concurrency < 1:
        raise ValueError("concurrency must be positive")
    batch_started = perf_counter()
    embed_seconds = 0.0
    context_seconds = 0.0
    model_seconds = 0.0
    commit_seconds = 0.0
    start = min(pub.published_at for pub, _ in jobs) - LOOKBACK
    pool = await store.fragments_since(start)
    links = await store.links_for_publications({item.publication_id for item in pool})
    entities = await store.list_entities()
    stories = await store.list_stories()
    events = await store.list_events()
    load_seconds = perf_counter() - batch_started
    frozen_pool = tuple(pool)
    frozen_links = tuple(links)
    frozen_entities = tuple(entities)
    frozen_stories = tuple(stories)
    frozen_events = tuple(events)
    semaphore = asyncio.Semaphore(concurrency)
    embedding_locks: dict[str, asyncio.Lock] = {}

    async def prepare(
        publication: PublicationVersion, extraction: ExtractionResult
    ) -> list[PreparedFragment]:
        nonlocal embed_seconds, context_seconds, model_seconds
        prepared: list[PreparedFragment] = []
        for index, fragment in enumerate(extraction.fragments):
            if not fragment.claims:
                continue
            surfaces = [entity.surface for entity in fragment.entities]
            key = embedding_cache_key(embedding_input(fragment.text, surfaces))
            started = perf_counter()
            async with embedding_locks.setdefault(key, asyncio.Lock()), semaphore:
                indexed = await _indexed_for(store, embedder, publication, index, fragment)
            embed_seconds += perf_counter() - started
            started = perf_counter()
            context = _context_from_state(
                indexed,
                frozen_pool,
                frozen_links,
                frozen_entities,
                frozen_stories,
                frozen_events,
            )
            context_seconds += perf_counter() - started
            started = perf_counter()
            try:
                async with semaphore:
                    assignment = await _decide(assigner, indexed, context)
            except BudgetExceeded:
                raise
            except Exception:
                assignment = None
            finally:
                model_seconds += perf_counter() - started
            prepared.append(PreparedFragment(index, fragment, indexed, context, assignment))
            if assignment is None:
                break
        return prepared

    tasks = [asyncio.create_task(prepare(pub, extraction)) for pub, extraction in jobs]
    try:
        proposals = await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    reused = 0
    retried = 0
    for (publication, _), prepared in zip(jobs, proposals, strict=True):
        failed = False
        for proposal in prepared:
            started = perf_counter()
            context = _context_from_state(proposal.indexed, pool, links, entities, stories, events)
            context_seconds += perf_counter() - started
            assignment = proposal.assignment
            if context != proposal.context:
                retried += 1
                started = perf_counter()
                try:
                    assignment = await _decide(assigner, proposal.indexed, context)
                except BudgetExceeded:
                    raise
                except Exception:
                    assignment = None
                finally:
                    model_seconds += perf_counter() - started
            else:
                reused += 1
            if assignment is None:
                await store.enqueue(publication.publication_id, "assign_error")
                failed = True
                break
            started = perf_counter()
            effect = await _apply_decision(
                store,
                publication,
                proposal.index,
                proposal.fragment,
                proposal.indexed,
                context,
                assignment,
            )
            commit_seconds += perf_counter() - started
            if not effect.valid:
                failed = True
                break
            for entity in effect.entities:
                entities = [item for item in entities if item.entity_id != entity.entity_id]
                entities.append(entity)
            if effect.story is not None:
                stories = [item for item in stories if item.story_id != effect.story.story_id]
                stories.append(effect.story)
            if effect.event is not None:
                events = [item for item in events if item.event_id != effect.event.event_id]
                events.append(effect.event)
            links.extend(effect.links)
            if effect.indexed is not None:
                pool.append(effect.indexed)
        if not failed:
            await store.mark_processed(publication.publication_id)
    _log.info(
        "agenda assign batch posts=%d reused=%d retried=%d load_seconds=%.1f "
        "embed_seconds=%.1f context_seconds=%.1f model_seconds=%.1f "
        "commit_seconds=%.1f wall_seconds=%.1f",
        len(jobs),
        reused,
        retried,
        load_seconds,
        embed_seconds,
        context_seconds,
        model_seconds,
        commit_seconds,
        perf_counter() - batch_started,
    )
    return reused, retried


def _resolve_story(
    assignment, stories: list[Story], publication: PublicationVersion
) -> Story | None:
    if assignment.story_decision == "ambiguous":
        return None
    if assignment.story_decision == "existing" and assignment.story_id:
        for story in stories:
            if story.story_id == assignment.story_id:
                return story
    title = assignment.title_ru.strip()
    if title.casefold() in {"", "сюжет"}:
        return None
    story_id = assignment.story_id or _stable_id("st", title)
    return Story(
        story_id=story_id,
        title_ru=title,
        boundary=assignment.boundary or title,
        first_seen=publication.published_at,
    )


def _resolve_event(assignment, story_id: str, events: list[Event]) -> str | None:
    decision = getattr(assignment, "event_decision", "separate")
    if decision == "existing" and assignment.event_id:
        return assignment.event_id
    when = getattr(assignment, "event_when", "")
    amount = getattr(assignment, "event_amount", "")
    if decision == "new" or (decision == "separate" and (when or amount)):
        return assignment.event_id or _stable_id("ev", story_id, when, amount)
    return None


def _link(
    story_id: str,
    publication: PublicationVersion,
    fragment_index: int,
    claim_index: int,
    claim: Claim,
    entities: list[Entity],
    event_id: str | None,
    paraphrase_ru: str,
) -> StoryLink:
    return StoryLink(
        story_id=story_id,
        publication_id=publication.publication_id,
        version=publication.version,
        fragment_index=fragment_index,
        claim_index=claim_index,
        event_id=event_id,
        entity_ids=tuple(entity.entity_id for entity in entities),
        kind=claim.kind,
        speaker=claim.speaker,
        quote=claim.quote,
        paraphrase_ru=paraphrase_ru,
    )
