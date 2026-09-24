import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.application import agenda_assign
from astrafeed.application.agenda_assign import (
    assign_publication,
    assign_speculative_batch,
    find_candidates,
)
from astrafeed.application.agenda_extract import analyze_publication
from astrafeed.application.agenda_snapshot import build_snapshot, publish_snapshot
from astrafeed.domain.agenda import (
    CLASSIFIER_VERSION,
    Claim,
    Entity,
    ExtractionResult,
    Fragment,
    IndexedFragment,
    MentionedEntity,
    PublicationVersion,
    Story,
    StoryLink,
    analysis_reuse_key,
    embedding_input,
    publication_id,
    text_hash,
    windows_at,
)


class Extractor:
    def __init__(self, by_text: dict[str, ExtractionResult]) -> None:
        self.by_text = by_text

    async def extract(self, text: str) -> ExtractionResult:
        return self.by_text[text]


class Embedder:
    def __init__(self, vectors: dict[str, list[float]] | Exception) -> None:
        self.vectors = vectors
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if isinstance(self.vectors, Exception):
            raise self.vectors
        return [self.vectors[text] for text in texts]


class Assigner:
    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls = 0

    async def assign(self, **kwargs):
        self.calls += 1
        result = self.handler(**kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result


def _pub(
    text: str, source_id: int, external_id: str, channel: str, when: datetime
) -> PublicationVersion:
    return PublicationVersion(
        publication_id=publication_id(source_id, external_id),
        source_id=source_id,
        external_id=external_id,
        text=text,
        text_hash=text_hash(text),
        published_at=when,
        detected_at=when,
        channel_ref=channel,
        link=f"https://t.me/{channel[1:]}/{external_id}",
    )


def _event_result(text: str, quote: str, entity: str) -> ExtractionResult:
    start = text.find(quote)
    return ExtractionResult(
        reuse_key=analysis_reuse_key(text_hash(text)),
        text_hash=text_hash(text),
        classifier_version=CLASSIFIER_VERSION,
        status="ok",
        fragments=(
            Fragment(
                text=quote,
                start=start,
                end=start + len(quote),
                entities=(MentionedEntity(entity, quote),),
                claims=(
                    Claim(
                        kind="event",
                        speaker="author",
                        quote=quote,
                        start=start,
                        end=start + len(quote),
                    ),
                ),
            ),
        ),
    )


def test_embedding_input_uses_fragment_and_entities_not_digest():
    digest = "1) ETF отток. 2) SOL листинг. 3) реклама курса."
    fragment = "ETF отток $120 млн"
    assert embedding_input(fragment, ["ETH ETF", "BlackRock"]) == (
        "ETF отток $120 млн\nEntities: ETH ETF, BlackRock"
    )
    assert digest not in embedding_input(fragment, ["ETH ETF"])


def test_assignment_context_contains_only_candidate_stories_and_matching_entities():
    now = datetime(2026, 9, 24, tzinfo=UTC)
    fragment = IndexedFragment(
        publication_id="new:1",
        published_at=now,
        fragment_index=0,
        text="Отток ETH ETF",
        entity_surfaces=("ETH ETF",),
        claim_text="Отток ETH ETF",
        vector=[1.0, 0.0],
    )
    candidate = IndexedFragment(
        publication_id="old:1",
        published_at=now - timedelta(hours=1),
        fragment_index=0,
        text="Отток ETH ETF",
        entity_surfaces=("ETH ETF",),
        claim_text="Отток ETH ETF",
        vector=[1.0, 0.0],
    )
    linked = StoryLink(
        story_id="relevant",
        publication_id="old:1",
        version=1,
        fragment_index=0,
        claim_index=0,
        event_id="event-relevant",
        entity_ids=("entity-relevant",),
    )
    unrelated = StoryLink(
        story_id="unrelated",
        publication_id="other:1",
        version=1,
        fragment_index=0,
        claim_index=0,
        event_id="event-unrelated",
        entity_ids=("entity-unrelated",),
    )
    entities = [
        Entity("entity-relevant", "Ethereum", aliases=("ETH ETF",)),
        Entity("entity-unrelated", "Solana", aliases=("SOL",)),
    ]
    stories = [
        Story("relevant", "Потоки ETH ETF", "ETF", now),
        Story("unrelated", "SOL", "SOL", now),
    ]
    events = [
        agenda_assign.Event("event-relevant", "relevant", "2026-09-23"),
        agenda_assign.Event("event-unrelated", "unrelated", "2026-09-23"),
    ]

    selected_entities, selected_stories, selected_events = agenda_assign.select_assignment_context(
        fragment, [candidate], [linked, unrelated], entities, stories, events
    )

    assert [entity.entity_id for entity in selected_entities] == ["entity-relevant"]
    assert [story.story_id for story in selected_stories] == ["relevant"]
    assert [event.event_id for event in selected_events] == ["event-relevant"]


def test_candidates_are_union_of_semantic_and_lexical_top_ten():
    now = datetime(2026, 9, 24, tzinfo=UTC)
    query = IndexedFragment(
        publication_id="q",
        published_at=now,
        fragment_index=0,
        text="отток ETH ETF",
        entity_surfaces=("ETH ETF",),
        claim_text="отток ETH ETF",
        vector=[1.0, 0.0],
    )
    pool = []
    for i in range(15):
        pool.append(
            IndexedFragment(
                publication_id=f"sem-{i}",
                published_at=now - timedelta(hours=i + 1),
                fragment_index=0,
                text=f"семантика {i}",
                entity_surfaces=(),
                claim_text=f"семантика {i}",
                vector=[0.9 - i * 0.01, 0.1],
            )
        )
    for i in range(15):
        pool.append(
            IndexedFragment(
                publication_id=f"lex-{i}",
                published_at=now - timedelta(hours=i + 1),
                fragment_index=0,
                text=f"отток ETH ETF повтор {i}",
                entity_surfaces=("ETH ETF",),
                claim_text=f"отток ETH ETF повтор {i}",
                vector=[0.0, 1.0],
            )
        )
    found = find_candidates(query, pool)
    ids = {f.publication_id for f in found}
    assert any(i.startswith("sem-") for i in ids)
    assert any(i.startswith("lex-") for i in ids)
    assert len(found) <= 20
    assert "q" not in ids


@pytest.mark.asyncio
async def test_speculative_assignment_revalidates_changed_story_context():
    from astrafeed.adapters.llm.agenda import Assignment

    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    first_text = "Отток ETH ETF составил 120 млн сегодня."
    second_text = "BlackRock сообщил об оттоке ETH ETF сегодня."
    first = _pub(first_text, 1, "1", "@a", now - timedelta(hours=2))
    second = _pub(second_text, 2, "2", "@b", now - timedelta(hours=1))
    for pub in (first, second):
        await store.record_publication(pub)

    class ConcurrentAssigner:
        active = 0
        maximum = 0
        calls = 0

        async def assign(self, **kwargs):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            self.calls += 1
            await asyncio.sleep(0.01)
            self.active -= 1
            stories = kwargs["stories"]
            return Assignment(
                entity_decisions=(),
                story_decision="existing" if stories else "new",
                story_id=stories[0].story_id if stories else None,
                title_ru="Потоки ETH ETF",
                boundary="ETH ETF",
                event_decision="separate",
                event_id=None,
            )

    assigner = ConcurrentAssigner()
    embedder = Embedder(
        {
            embedding_input(first_text, ["ETH"]): [1.0, 0.0],
            embedding_input(second_text, ["ETH"]): [1.0, 0.0],
        }
    )
    reused, retried = await assign_speculative_batch(
        store,
        embedder,
        assigner,
        [
            (first, _event_result(first_text, first_text, "ETH")),
            (second, _event_result(second_text, second_text, "ETH")),
        ],
        concurrency=2,
    )

    assert assigner.maximum == 2
    assert (reused, retried) == (1, 1)
    assert assigner.calls == 3
    links = await store.links_for_publications({first.publication_id, second.publication_id})
    assert len({link.story_id for link in links}) == 1
    assert await store.queue_depth() == 0


@pytest.mark.asyncio
async def test_embedding_failure_keeps_queue_and_does_not_assign():
    store = InMemoryAgendaStore()
    when = datetime(2026, 9, 23, 12, tzinfo=UTC)
    text = "Отток ETH ETF составил 120 млн."
    pub = _pub(text, 1, "1", "@a", when)
    await store.record_publication(pub)
    extraction = _event_result(text, "Отток ETH ETF составил 120 млн.", "ETH ETF")
    await analyze_publication(store, Extractor({text: extraction}), pub)
    assigner = Assigner(lambda **kwargs: (_ for _ in ()).throw(AssertionError("no assign")))
    with pytest.raises(RuntimeError, match="embeddings down"):
        await assign_publication(
            store,
            Embedder(RuntimeError("embeddings down")),
            assigner,
            pub,
            extraction,
        )
    assert store.queue_reason(pub.publication_id) == "embed_error"
    assert assigner.calls == 0


@pytest.mark.asyncio
async def test_one_channel_one_vote_and_edit_does_not_rewrite_old_snapshot():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)
    current, _previous = windows_at(t)
    texts = {
        "alpha": "Отток ETH ETF составил 120 млн.",
        "beta": "BlackRock зафиксировал отток ETH ETF на 120 млн.",
    }
    pubs = [
        _pub(texts["alpha"], 1, "10", "@alpha", current[0] + timedelta(hours=2)),
        _pub(texts["alpha"], 1, "11", "@alpha", current[0] + timedelta(hours=3)),
        _pub(texts["beta"], 2, "7", "@beta", current[0] + timedelta(hours=4)),
    ]
    extractor = Extractor(
        {
            texts["alpha"]: _event_result(texts["alpha"], "Отток ETH ETF составил 120 млн.", "ETH"),
            texts["beta"]: _event_result(
                texts["beta"], "BlackRock зафиксировал отток ETH ETF на 120 млн.", "ETH"
            ),
        }
    )
    embedder = Embedder(
        {
            embedding_input("Отток ETH ETF составил 120 млн.", ["ETH"]): [1.0, 0.0],
            embedding_input("BlackRock зафиксировал отток ETH ETF на 120 млн.", ["ETH"]): [
                0.95,
                0.05,
            ],
        }
    )

    async def handler(**kwargs):
        from astrafeed.adapters.llm.agenda import Assignment

        return Assignment(
            entity_decisions=(("ETH", "new", None, "Ethereum"),),
            story_decision="existing" if kwargs["stories"] else "new",
            story_id=kwargs["stories"][0].story_id if kwargs["stories"] else None,
            title_ru="Потоки ETH ETF",
            boundary="Притоки и оттоки спотовых ETH ETF",
            event_decision="new",
            event_id=None,
            event_when="",
            paraphrase_ru="Пишут об оттоке ETH ETF",
        )

    assigner = Assigner(handler)
    for pub in pubs:
        await store.record_publication(pub)
        extraction = await analyze_publication(store, extractor, pub)
        await assign_publication(store, embedder, assigner, pub, extraction)

    coverage = {
        1: {"current_complete": True, "previous_complete": True, "processed": True},
        2: {"current_complete": True, "previous_complete": True, "processed": True},
    }
    snap = await build_snapshot(store, t, coverage, collected_at=t, analyzed_at=t)
    await publish_snapshot(store, snap)
    first = await store.get_snapshot(None)
    assert first is not None
    card = first.agenda[0]
    assert card.current_channels == 2
    assert card.growth == 2
    assert card.claims

    edited = _pub(
        "Отток ETH ETF составил 999 млн. Это новая цифра.",
        1,
        "10",
        "@alpha",
        pubs[1].published_at,
    )
    await store.record_publication(edited)
    frozen = await store.get_snapshot(first.snapshot_id)
    assert frozen is not None
    assert frozen.agenda[0].claims[0].quote != "Отток ETH ETF составил 999 млн. Это новая цифра."
    assert "999" not in frozen.agenda[0].explanation


@pytest.mark.asyncio
async def test_new_channel_without_backfill_does_not_create_growth():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)
    current, _ = windows_at(t)
    await store.save_story(Story("st-eth", "Потоки ETH ETF", "ETF", first_seen=current[0]))
    await store.save_entity(Entity("en-eth", "Ethereum", aliases=("ETH",)))
    for source_id, channel, external in ((1, "@a", "1"), (3, "@new", "2")):
        pub = _pub("Отток ETH ETF составил 120 млн.", source_id, external, channel, current[0])
        await store.record_publication(pub)
        await store.save_link(
            StoryLink(
                story_id="st-eth",
                publication_id=pub.publication_id,
                version=1,
                fragment_index=0,
                claim_index=0,
                quote="Отток ETH ETF составил 120 млн.",
                paraphrase_ru="Пишут об оттоке",
            )
        )
    coverage = {
        1: {"current_complete": True, "previous_complete": True, "processed": True},
        3: {"current_complete": True, "previous_complete": False, "processed": True},
    }
    snap = await build_snapshot(store, t, coverage, collected_at=t, analyzed_at=t)
    card = snap.stories["st-eth"].card
    assert card.growth is None
    assert card.growth_null_reason == "comparable_channels_below_2"
    assert card.current_channels == 2
