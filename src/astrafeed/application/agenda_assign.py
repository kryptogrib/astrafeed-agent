"""Embed fragments, collect candidates, and apply story assignment."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
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
from astrafeed.ports.agenda import AgendaStore, Embedder, StoryAssigner


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
        link
        for link in links
        if (link.publication_id, link.fragment_index) in candidate_keys
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
        surfaces = [entity.surface for entity in fragment.entities]
        text = embedding_input(fragment.text, surfaces)
        try:
            vector = await _vector_for(store, embedder, text)
        except Exception:
            await store.enqueue(publication.publication_id, "embed_error")
            raise
        indexed = IndexedFragment(
            publication_id=publication.publication_id,
            published_at=publication.published_at,
            fragment_index=index,
            text=fragment.text,
            entity_surfaces=tuple(surfaces),
            claim_text=_claim_text(fragment),
            vector=vector,
        )
        pool = [
            item
            for item in await store.fragments_since(publication.published_at - LOOKBACK)
            if item.published_at < publication.published_at
        ]
        candidates = find_candidates(indexed, pool)
        links = await store.links_for_publications(
            {candidate.publication_id for candidate in candidates}
        )
        entities, stories, events = select_assignment_context(
            indexed,
            candidates,
            links,
            await store.list_entities(),
            await store.list_stories(),
            await store.list_events(),
        )
        assignment = await assigner.assign(
            fragment=indexed,
            entities=entities,
            stories=stories,
            events=events,
            candidates=candidates,
        )
        chosen_entities = _apply_entities(entities, assignment)
        for entity in chosen_entities:
            await store.save_entity(entity)
        story = _resolve_story(assignment, stories, publication)
        if story is None:
            continue
        await store.save_story(story)
        event_id = _resolve_event(assignment, story.story_id, events)
        if event_id:
            await store.save_event(
                Event(
                    event_id=event_id,
                    story_id=story.story_id,
                    when=getattr(assignment, "event_when", ""),
                    amount=getattr(assignment, "event_amount", ""),
                )
            )
        for claim_index, claim in enumerate(fragment.claims):
            await store.save_link(
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
            )
        await store.index_fragment(indexed)
    await store.mark_processed(publication.publication_id)


def _resolve_story(
    assignment, stories: list[Story], publication: PublicationVersion
) -> Story | None:
    if assignment.story_decision == "ambiguous":
        return None
    if assignment.story_decision == "existing" and assignment.story_id:
        for story in stories:
            if story.story_id == assignment.story_id:
                return story
    title = assignment.title_ru or assignment.boundary or "Сюжет"
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
