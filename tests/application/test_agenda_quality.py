from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.llm.agenda import Assignment
from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.application.agenda_assign import assign_publication
from astrafeed.application.agenda_extract import verify_fragment
from astrafeed.application.agenda_snapshot import build_snapshot
from astrafeed.domain.agenda import (
    Claim,
    Entity,
    ExtractionResult,
    Fragment,
    PublicationVersion,
    Story,
    StoryLink,
    text_hash,
)


def _publication(source_id: int, external_id: str, text: str, when: datetime) -> PublicationVersion:
    return PublicationVersion(
        publication_id=f"{source_id}:{external_id}",
        source_id=source_id,
        external_id=external_id,
        text=text,
        text_hash=text_hash(text),
        published_at=when,
        detected_at=when,
        channel_ref=f"@channel{source_id}",
        link=f"https://t.me/channel{source_id}/{external_id}",
    )


def _coverage() -> dict[int, dict[str, bool]]:
    return {
        source_id: {"current_complete": True, "previous_complete": True, "processed": True}
        for source_id in (1, 2)
    }


async def _link(
    store: InMemoryAgendaStore,
    story_id: str,
    publication: PublicationVersion,
    quote: str,
    paraphrase: str,
    claim_index: int = 0,
    entity_ids: tuple[str, ...] = (),
) -> None:
    await store.save_link(
        StoryLink(
            story_id=story_id,
            publication_id=publication.publication_id,
            version=publication.version,
            fragment_index=0,
            claim_index=claim_index,
            entity_ids=entity_ids,
            quote=quote,
            paraphrase_ru=paraphrase,
        )
    )


def test_verified_extraction_drops_navigation_short_and_promotional_claims():
    quotes = (
        "Ранее:\n- AI-царь Белого дома\n- потеря контроля",
        "ТОП ДНЯ",
        "Подпишись на наш закрытый канал",
        "Payy, возможно, взломан на $1,83 млн.",
    )
    text = "\n".join(quotes)
    claims = tuple(
        Claim(
            kind="explicit_call" if index == 2 else "event",
            speaker="author",
            quote=quote,
            start=text.index(quote),
            end=text.index(quote) + len(quote),
            is_ad=index == 2,
        )
        for index, quote in enumerate(quotes)
    )
    fragment = Fragment(text=text, start=0, end=len(text), claims=claims)

    verified = verify_fragment(text, fragment)

    assert [claim.quote for claim in verified.claims] == [quotes[-1]]


@pytest.mark.asyncio
async def test_new_story_requires_specific_title_and_keeps_post_queued():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    quote = "Payy, возможно, взломан на $1,83 млн."
    pub = _publication(1, "1", quote, now)
    await store.record_publication(pub)
    extraction = ExtractionResult(
        reuse_key="key",
        text_hash=pub.text_hash,
        classifier_version="v1",
        status="ok",
        fragments=(
            Fragment(
                text=quote,
                start=0,
                end=len(quote),
                claims=(
                    Claim(kind="event", speaker="author", quote=quote, start=0, end=len(quote)),
                ),
            ),
        ),
    )

    class Embedder:
        async def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    class Assigner:
        async def assign(self, **kwargs):
            return Assignment((), "new", None, "Сюжет", "Payy", "separate", None)

    await assign_publication(store, Embedder(), Assigner(), pub, extraction)

    assert await store.list_stories() == []
    assert store.queue_reason(pub.publication_id) == "assign_error"


@pytest.mark.asyncio
async def test_generic_story_title_is_not_published_in_agenda():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await store.save_story(Story("generic", "Сюжет", "", now - timedelta(hours=2)))
    for source_id in (1, 2):
        quote = "Кто-то отчеканил более миллиарда MTRG."
        pub = _publication(source_id, str(source_id), quote, now - timedelta(hours=1))
        await store.record_publication(pub)
        await _link(store, "generic", pub, quote, quote)

    snapshot = await build_snapshot(store, now, _coverage(), collected_at=now, analyzed_at=now)

    assert snapshot.agenda == ()


@pytest.mark.asyncio
async def test_navigation_claim_does_not_create_a_second_channel_vote():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await store.save_story(Story("sec", "SEC прекратила крипторасследования", "SEC", now))
    navigation = "Ранее:\n- AI-царь Белого дома\n- потеря контроля"
    real = "SEC прекратила расследования по криптовалютным делам."
    for source_id, quote in ((1, navigation), (2, real)):
        pub = _publication(source_id, str(source_id), quote, now - timedelta(hours=1))
        await store.record_publication(pub)
        await _link(store, "sec", pub, quote, quote)

    snapshot = await build_snapshot(store, now, _coverage(), collected_at=now, analyzed_at=now)

    assert snapshot.agenda == ()
    assert snapshot.stories["sec"].card.current_channels == 1


@pytest.mark.asyncio
async def test_unprocessed_channels_count_as_incomplete():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    coverage = _coverage()
    coverage[2]["processed"] = False

    snapshot = await build_snapshot(store, now, coverage, collected_at=now, analyzed_at=now)

    assert snapshot.coverage.channels_ok == 1
    assert snapshot.coverage.channels_incomplete == 1
    assert snapshot.coverage.comparable_channels == 1


@pytest.mark.asyncio
async def test_payy_card_uses_one_relevant_summary_and_quotes_from_both_sources():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await store.save_story(Story("payy", "Payy, возможно, взломан на $1,83 млн", "Payy", now))
    payy = "Хакер взломал криптопроект Payy на $1,83 млн."
    duelbits = "Криптоказино Duelbits также взломано на $4,3 млн."
    first = _publication(1, "1", payy + "\n" + duelbits, now - timedelta(hours=2))
    second_quote = "Payy, возможно, взломан на $1,83 млн."
    second = _publication(2, "2", second_quote, now - timedelta(hours=1))
    await store.record_publication(first)
    await store.record_publication(second)
    await _link(store, "payy", first, payy, "Payy взломан на $1,83 млн")
    await _link(store, "payy", first, duelbits, "Duelbits взломан на $4,3 млн", 1)
    await _link(store, "payy", second, second_quote, "Сообщают о взломе Payy на $1,83 млн")

    snapshot = await build_snapshot(store, now, _coverage(), collected_at=now, analyzed_at=now)

    assert len(snapshot.agenda) == 1
    card = snapshot.agenda[0]
    assert card.explanation == payy
    assert all("Duelbits" not in claim.quote for claim in card.claims)
    assert {claim.channel_ref for claim in card.claims} == {"@channel1", "@channel2"}


@pytest.mark.asyncio
async def test_ungrounded_numeric_title_is_not_published_in_agenda():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await store.save_story(Story("otc", "ОТС-кит купил 15 000 ETH", "ETH", now))
    quote = "ОТС-кит продал 42 005 ETH и оставил 9 996 ETH."
    for source_id in (1, 2):
        pub = _publication(source_id, str(source_id), quote, now - timedelta(hours=1))
        await store.record_publication(pub)
        await _link(store, "otc", pub, quote, quote)

    snapshot = await build_snapshot(store, now, _coverage(), collected_at=now, analyzed_at=now)

    assert snapshot.agenda == ()
    assert "otc" not in snapshot.stories


@pytest.mark.asyncio
async def test_unrelated_link_never_votes_or_appears_in_story_detail():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await store.save_story(
        Story("round", "infiniFi привлекли $3 млн", "", now, key_entity="infinifi")
    )
    for source_id, quote in (
        (1, "infiniFi привлекли $3 млн от Electric Capital."),
        (2, "тге в q4 анонсировали"),
    ):
        pub = _publication(source_id, str(source_id), quote, now - timedelta(hours=1))
        await store.record_publication(pub)
        await _link(store, "round", pub, quote, quote)
    snapshot = await build_snapshot(store, now, _coverage(), collected_at=now, analyzed_at=now)
    detail = snapshot.stories["round"]
    assert detail.card.current_channels == 1
    assert [claim.quote for claim in detail.card.claims] == [
        "infiniFi привлекли $3 млн от Electric Capital."
    ]
    assert len(detail.publications) == 1
    assert snapshot.agenda == ()


@pytest.mark.asyncio
async def test_lit_fdv_does_not_vote_for_polymarket_story():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await store.save_story(Story("poly", "Polymarket оценивает FDV $1-2 млрд", "", now))
    for source_id, quote in (
        (1, "На Polymarket оценивают токен по $1-2 млрд FDV."),
        (2, "$LIT 5.3b FDV"),
    ):
        pub = _publication(source_id, str(source_id), quote, now - timedelta(hours=1))
        await store.record_publication(pub)
        await _link(store, "poly", pub, quote, quote)
    snapshot = await build_snapshot(store, now, _coverage(), collected_at=now, analyzed_at=now)
    assert snapshot.stories["poly"].card.current_channels == 1


@pytest.mark.asyncio
async def test_confirmed_project_is_named_and_profane_paraphrase_is_not_explanation():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await store.save_entity(Entity("variational", "Variational"))
    await store.save_story(
        Story("points", "Программа поинтов продлена до TGE", "", now, key_entity="variational")
    )
    quote = "Variational продлили программу поинтов до TGE."
    for source_id in (1, 2):
        pub = _publication(source_id, str(source_id), quote, now - timedelta(hours=1))
        await store.record_publication(pub)
        await _link(
            store, "points", pub, quote, "нас наебали с поинтами",
            entity_ids=("variational",),
        )
    snapshot = await build_snapshot(store, now, _coverage(), collected_at=now, analyzed_at=now)
    card = snapshot.agenda[0]
    assert card.title.startswith("Variational:")
    assert card.explanation == quote


@pytest.mark.asyncio
async def test_story_evidence_verification_removes_false_channel_vote():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await store.save_story(Story("hormuz", "Десять судов прошли Ормузский пролив", "", now))
    quotes = (
        "Десять судов прошли Ормузский пролив в среду.",
        "Катар увеличил поток танкеров через Ормузский пролив.",
    )
    for source_id, quote in enumerate(quotes, 1):
        pub = _publication(source_id, str(source_id), quote, now - timedelta(hours=1))
        await store.record_publication(pub)
        await _link(store, "hormuz", pub, quote, quote)

    class Verifier:
        calls = 0

        async def verify(self, story, quotes):
            self.calls += 1
            return [quote.startswith("Десять") for quote in quotes]

    verifier = Verifier()
    first = await build_snapshot(
        store, now, _coverage(), collected_at=now, analyzed_at=now, verifier=verifier
    )
    second = await build_snapshot(
        store, now, _coverage(), collected_at=now, analyzed_at=now, verifier=verifier
    )
    assert first.stories["hormuz"].card.current_channels == 1
    assert first.stories["hormuz"].card.growth == 1
    assert first.agenda == ()
    assert second.stories["hormuz"].card.current_channels == 1
    assert verifier.calls == 1


@pytest.mark.asyncio
async def test_subjectless_excerpt_cannot_vote_for_named_project():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 24, 12, tzinfo=UTC)
    await store.save_entity(Entity("variational", "Variational"))
    await store.save_story(Story("beta", "Завершение закрытого бета-тестирования", "", now))
    for source_id in (1, 2):
        quote = "Завершение закрытого бета-тестирования"
        pub = _publication(source_id, str(source_id), "Variational: " + quote, now)
        await store.record_publication(pub)
        await _link(store, "beta", pub, quote, quote)
    snapshot = await build_snapshot(store, now + timedelta(minutes=1), _coverage(),
                                    collected_at=now, analyzed_at=now)
    assert "beta" not in snapshot.stories
