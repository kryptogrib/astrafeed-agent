"""Compute comparable-window metrics and publish an immutable snapshot."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from astrafeed.domain.agenda import (
    ClaimCard,
    CoverageInfo,
    EventCard,
    PositionCard,
    PublicationRef,
    PublicationVersion,
    SearchDoc,
    Snapshot,
    StoryCard,
    StoryDetail,
    StoryLink,
    comparable_channel_ids,
    decide_growth,
    in_window,
    numbers_are_grounded,
    select_agenda,
    windows_at,
)
from astrafeed.ports.agenda import AgendaStore


def _snapshot_id(t: datetime) -> str:
    return "snap-" + t.strftime("%Y%m%dT%H%M%SZ")


def _votes(
    links: list[StoryLink],
    publications: dict[str, PublicationVersion],
    window: tuple[datetime, datetime],
    allowed: set[int] | None,
) -> list[PublicationVersion]:
    found: list[PublicationVersion] = []
    seen_channels: set[int] = set()
    for link in links:
        pub = publications.get(link.publication_id)
        if pub is None or not in_window(pub.published_at, window):
            continue
        if allowed is not None and pub.source_id not in allowed:
            continue
        found.append(pub)
        seen_channels.add(pub.source_id)
    return found


def _unique_channels(pubs: list[PublicationVersion]) -> set[int]:
    return {pub.source_id for pub in pubs}


def _hashes(pubs: list[PublicationVersion]) -> list[str]:
    return [pub.text_hash for pub in pubs]


def _explanation(claims: list[ClaimCard]) -> str:
    parts = [claim.paraphrase_ru or claim.quote for claim in claims[:3]]
    text = " ".join(part for part in parts if part)
    quotes = [claim.quote for claim in claims]
    if text and not numbers_are_grounded(text, quotes):
        return " ".join(quotes[:2])
    return text


def _claim_cards(
    links: list[StoryLink],
    publications: dict[str, PublicationVersion],
    window: tuple[datetime, datetime],
) -> list[ClaimCard]:
    cards: list[ClaimCard] = []
    seen_channels: set[str] = set()
    for link in links:
        pub = publications.get(link.publication_id)
        if pub is None or not in_window(pub.published_at, window):
            continue
        paraphrase = link.paraphrase_ru
        if paraphrase and not numbers_are_grounded(paraphrase, [link.quote]):
            paraphrase = link.quote
        card = ClaimCard(
            kind=link.kind,
            speaker=link.speaker,
            quote=link.quote,
            paraphrase_ru=paraphrase,
            link=pub.link,
            channel_ref=pub.channel_ref,
            published_at=pub.published_at,
        )
        if pub.channel_ref not in seen_channels or len(cards) < 3:
            cards.append(card)
            seen_channels.add(pub.channel_ref)
        if len(cards) >= 3:
            break
    return cards


async def build_snapshot(
    store: AgendaStore,
    t: datetime,
    coverage_states: dict[int, dict[str, bool]],
    *,
    collected_at: datetime,
    analyzed_at: datetime,
    failed_channels: int = 0,
) -> Snapshot:
    current, previous = windows_at(t)
    pubs = [
        pub
        for pub in await store.publications_in(previous[0], current[1])
        if pub.source_id in coverage_states
    ]
    by_id = {pub.publication_id: pub for pub in pubs}
    stories = {story.story_id: story for story in await store.list_stories()}
    events = await store.list_events()
    entities = {entity.entity_id: entity for entity in await store.list_entities()}
    all_links = await store.links_for_publications(set(by_id))
    links_by_story: dict[str, list[StoryLink]] = defaultdict(list)
    for link in all_links:
        links_by_story[link.story_id].append(link)
    comparable = comparable_channel_ids(coverage_states)
    details: dict[str, StoryDetail] = {}
    cards: list[dict] = []
    for story_id, links in links_by_story.items():
        story = stories.get(story_id)
        if story is None:
            continue
        current_all = _votes(links, by_id, current, None)
        current_cmp = _votes(links, by_id, current, set(comparable))
        previous_cmp = _votes(links, by_id, previous, set(comparable))
        current_channels = len(_unique_channels(current_all))
        previous_channels = len(_unique_channels(previous_cmp))
        growth, reason = decide_growth(
            current_channels=len(_unique_channels(current_cmp)),
            previous_channels=previous_channels,
            comparable_count=len(comparable),
            previous_window_complete=len(comparable) >= 2,
        )
        hashes = _hashes(current_all)
        exact_repeats = max(0, len(hashes) - len(set(hashes)))
        claim_cards = _claim_cards(links, by_id, current)
        entity_names = []
        for link in links:
            for entity_id in link.entity_ids:
                entity = entities.get(entity_id)
                name = entity.canonical_name if entity is not None else ""
                if name and name not in entity_names:
                    entity_names.append(name)
        freshness = max((pub.published_at for pub in current_all), default=story.first_seen)
        story_events = [event for event in events if event.story_id == story_id]
        positions = [
            PositionCard(
                speaker=link.speaker,
                channel_ref=by_id[link.publication_id].channel_ref,
                quote=link.quote,
                paraphrase_ru=link.paraphrase_ru,
                link=by_id[link.publication_id].link,
            )
            for link in links
            if link.kind == "author_position" and link.publication_id in by_id
        ]
        publications = [
            PublicationRef(
                publication_id=pub.publication_id,
                channel_ref=pub.channel_ref,
                link=pub.link,
                published_at=pub.published_at,
                quote=next(
                    (link.quote for link in links if link.publication_id == pub.publication_id),
                    "",
                ),
            )
            for pub in current_all
        ]
        card = StoryCard(
            story_id=story.story_id,
            title=story.title_ru,
            entities=tuple(entity_names),
            current_channels=current_channels,
            previous_channels=previous_channels if len(comparable) >= 2 else None,
            growth=growth,
            growth_null_reason=reason,
            first_seen=story.first_seen,
            freshness=freshness,
            explanation=_explanation(claim_cards),
            claims=tuple(claim_cards),
            publications=len(current_all),
            exact_repeats=exact_repeats,
            retellings=max(0, len(current_all) - len(set(hashes))),
            event_count=len(story_events),
            position_count=len(positions),
        )
        details[story.story_id] = StoryDetail(
            card=card,
            events=tuple(
                EventCard(
                    event_id=event.event_id,
                    when=event.when,
                    amount=event.amount,
                    participants=event.participants,
                )
                for event in story_events
            ),
            positions=tuple(positions),
            publications=tuple(publications),
        )
        cards.append(
            {
                "story_id": card.story_id,
                "growth": card.growth,
                "current_channels": card.current_channels,
                "previous_channels": card.previous_channels,
                "freshness": card.freshness,
                "eligible": True,
                "card": card,
            }
        )
    selected, mode = select_agenda(cards, len(comparable))
    agenda = tuple(item["card"] for item in selected)
    docs: list[SearchDoc] = []
    for detail in details.values():
        docs.append(SearchDoc(detail.card.story_id, "title", detail.card.title))
        for name in detail.card.entities:
            docs.append(SearchDoc(detail.card.story_id, "entity", name))
        for claim in detail.card.claims:
            docs.append(SearchDoc(detail.card.story_id, "claim", claim.quote))
        for pub in detail.publications:
            docs.append(SearchDoc(detail.card.story_id, "publication", pub.quote or pub.link))
    for entity in entities.values():
        for alias in entity.aliases:
            for detail in details.values():
                if entity.canonical_name in detail.card.entities:
                    docs.append(SearchDoc(detail.card.story_id, "alias", alias))
                    break
    processed = {pub.publication_id for pub in pubs}
    queued = set(await store.queued_ids()) & processed
    coverage = CoverageInfo(
        channels_ok=sum(1 for state in coverage_states.values() if state.get("processed")),
        channels_failed=failed_channels,
        channels_incomplete=sum(
            1
            for state in coverage_states.values()
            if not (state.get("current_complete") and state.get("previous_complete"))
        ),
        publications_total=len(pubs),
        publications_processed=len(processed - queued),
        publications_queued=len(queued),
        publications_failed=sum(1 for pid in queued if True),
        comparable_channels=len(comparable),
        limitations=()
        if mode == "full"
        else (
            ("too_few_comparable_channels",)
            if mode == "limited_no_growth_claim"
            else ("no_new_or_growing_stories",)
        ),
    )
    return Snapshot(
        snapshot_id=_snapshot_id(t),
        t=t,
        collected_at=collected_at,
        analyzed_at=analyzed_at,
        published_at=t,
        coverage=coverage,
        queue_depth=len(queued),
        limitations=coverage.limitations,
        agenda=agenda,
        agenda_mode=mode,
        stories=details,
        search_docs=tuple(docs),
    )


async def publish_snapshot(store: AgendaStore, snapshot: Snapshot) -> None:
    await store.publish_snapshot(snapshot)
