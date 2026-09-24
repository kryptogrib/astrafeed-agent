from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.llm.agenda import Assignment
from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.application.agenda_assign import assign_publication
from astrafeed.application.agenda_extract import verify_fragment
from astrafeed.application.agenda_snapshot import build_snapshot
from astrafeed.domain.agenda import (
    Claim,
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
) -> None:
    await store.save_link(
        StoryLink(
            story_id=story_id,
            publication_id=publication.publication_id,
            version=publication.version,
            fragment_index=0,
            claim_index=claim_index,
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
    assert card.explanation == "Payy взломан на $1,83 млн"
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
    assert snapshot.stories["otc"].card.current_channels == 2
