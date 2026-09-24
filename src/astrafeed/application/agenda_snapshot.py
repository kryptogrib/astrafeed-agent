"""Compute comparable-window metrics and publish an immutable snapshot."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

from astrafeed.application.agenda_extract import claim_is_noise
from astrafeed.domain.agenda import (
    ClaimCard,
    CoverageInfo,
    Entity,
    EventCard,
    PositionCard,
    PublicationRef,
    PublicationVersion,
    SearchDoc,
    Snapshot,
    Story,
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

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_PROFANITY = re.compile(r"(?:на[её]б|за[её]б|[её]бан|\bбля|\bхуй|\bху[её]в|\bпизд)", re.I)


def _supported_link(
    link: StoryLink,
    pub: PublicationVersion,
    title: str,
    key_entity: str,
    entities: dict[str, Entity],
) -> bool:
    """Only evidence that visibly names the subject can contribute a channel vote.

    This is deliberately conservative for old speculative assignments: a
    correct entity label or similar embedding cannot repair an unrelated quote.
    """
    quote = link.quote.strip()
    if not quote or quote not in pub.text:
        return False
    if key_entity and len(key_entity) >= 3:
        entity = next(
            (
                item
                for item in entities.values()
                if item.status == "confirmed"
                and item.canonical_name.casefold() == key_entity.casefold()
            ),
            None,
        )
        names = (key_entity, *(entity.aliases if entity else ()))
        if (key_entity.casefold() in title.casefold() or entity is not None) and not any(
            len(name) >= 3 and name.casefold() in quote.casefold() for name in names
        ):
            return False
    title_numbers = set(_NUMBER.findall(title))
    return not title_numbers or bool(title_numbers.intersection(_NUMBER.findall(quote)))


def _snapshot_id(t: datetime) -> str:
    return "snap-" + t.strftime("%Y%m%dT%H%M%SZ")


def _display_title(
    story: Story, links: list[StoryLink], entities: dict[str, Entity]
) -> tuple[str, str]:
    key = story.key_entity.casefold()
    primary = next(
        (
            entity
            for entity in entities.values()
            if entity.status == "confirmed" and entity.canonical_name.casefold() == key
        ),
        None,
    )
    title = story.title_ru.strip()
    if _PROFANITY.search(title):
        title = next(
            (
                value
                for link in links
                for value in (link.paraphrase_ru, link.quote)
                if value and not _PROFANITY.search(value)
                and numbers_are_grounded(value, [link.quote])
            ),
            "Сюжет",
        )
    if primary is None:
        return title, ""
    names = (primary.canonical_name, *primary.aliases)
    if any(name.casefold() in title.casefold() for name in names if len(name) >= 3):
        return title, key
    if any(
        name.casefold() in link.quote.casefold()
        for name in names if len(name) >= 3
        for link in links
    ):
        return f"{primary.canonical_name}: {title}", key
    return title, key


def _votes(
    links: list[StoryLink],
    publications: dict[str, PublicationVersion],
    window: tuple[datetime, datetime],
    allowed: set[int] | None,
) -> list[PublicationVersion]:
    found: list[PublicationVersion] = []
    seen_publications: set[str] = set()
    for link in links:
        pub = publications.get(link.publication_id)
        if pub is None or not in_window(pub.published_at, window):
            continue
        if allowed is not None and pub.source_id not in allowed:
            continue
        if pub.publication_id in seen_publications:
            continue
        found.append(pub)
        seen_publications.add(pub.publication_id)
    return found


def _unique_channels(pubs: list[PublicationVersion]) -> set[int]:
    return {pub.source_id for pub in pubs}


def _hashes(pubs: list[PublicationVersion]) -> list[str]:
    return [pub.text_hash for pub in pubs]


def _explanation(claims: list[ClaimCard], title: str) -> str:
    for claim in claims:
        for text in (claim.paraphrase_ru, claim.quote):
            if text and not _PROFANITY.search(text) and numbers_are_grounded(text, [claim.quote]):
                return text
    return title


def _title_terms(title: str) -> set[str]:
    latin = {word.casefold() for word in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", title)}
    if latin:
        return latin
    generic = {"возможно", "сегодня", "токен", "рынок", "крипто", "миллион", "миллиарда"}
    return {
        word.casefold()
        for word in re.findall(r"[А-Яа-яЁё]{5,}", title)
        if word.casefold() not in generic
    }


def _claim_cards(
    links: list[StoryLink],
    publications: dict[str, PublicationVersion],
    window: tuple[datetime, datetime],
    title: str,
) -> list[ClaimCard]:
    candidates: list[tuple[int, StoryLink, PublicationVersion]] = []
    terms = _title_terms(title)
    for link in links:
        pub = publications.get(link.publication_id)
        if pub is None or not in_window(pub.published_at, window):
            continue
        words = {
            word.casefold()
            for word in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", link.quote + " " + link.paraphrase_ru)
        }
        candidates.append((len(terms & words), link, pub))
    if any(score > 0 for score, _, _ in candidates):
        candidates = [candidate for candidate in candidates if candidate[0] > 0]
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    chosen: list[tuple[int, StoryLink, PublicationVersion]] = []
    seen_channels: set[str] = set()
    for candidate in candidates:
        channel = candidate[2].channel_ref
        if channel not in seen_channels:
            chosen.append(candidate)
            seen_channels.add(channel)
        if len(chosen) >= 3:
            break
    for candidate in candidates:
        if len(chosen) >= 3:
            break
        if candidate not in chosen:
            chosen.append(candidate)
    cards: list[ClaimCard] = []
    for _, link, pub in chosen:
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
        cards.append(card)
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
        story = stories.get(link.story_id)
        pub = by_id.get(link.publication_id)
        if (story is not None and pub is not None and not claim_is_noise(link.quote)
            and _supported_link(link, pub, story.title_ru, story.key_entity or "", entities)):
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
        title, primary_entity = _display_title(story, links, entities)
        claim_cards = _claim_cards(links, by_id, current, title)
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
            title=title,
            entities=tuple(entity_names),
            current_channels=current_channels,
            previous_channels=previous_channels if len(comparable) >= 2 else None,
            growth=growth,
            growth_null_reason=reason,
            first_seen=story.first_seen,
            freshness=freshness,
            explanation=_explanation(claim_cards, title),
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
                "eligible": title.casefold() not in {"", "сюжет"}
                and not _PROFANITY.search(title)
                and numbers_are_grounded(title, [claim.quote for claim in claim_cards]),
                "primary_entity": primary_entity,
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
            source = by_id.get(pub.publication_id)
            docs.append(
                SearchDoc(
                    detail.card.story_id,
                    "publication",
                    source.text if source is not None else pub.quote,
                )
            )
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
            if not (
                state.get("current_complete")
                and state.get("previous_complete")
                and state.get("processed")
            )
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
