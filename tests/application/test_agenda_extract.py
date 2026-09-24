from datetime import UTC, datetime

import pytest

from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.application.agenda_extract import analyze_publication
from astrafeed.domain.agenda import (
    CLASSIFIER_VERSION,
    Claim,
    ExtractionResult,
    Fragment,
    MentionedEntity,
    PublicationVersion,
    analysis_reuse_key,
    publication_id,
    text_hash,
)


def test_digest_claims_with_different_projects_become_separate_fragments():
    from astrafeed.application.agenda_extract import split_independent_claims
    from astrafeed.domain.agenda import Claim, Fragment, MentionedEntity

    text = "Plasma открыл тест. CypherSquad объявил минт."
    claims = (
        Claim("event", "author", "Plasma открыл тест.", 0, 19),
        Claim("event", "author", "CypherSquad объявил минт.", 20, len(text)),
    )
    fragment = Fragment(
        text=text,
        start=0,
        end=len(text),
        entities=(MentionedEntity("Plasma", ""), MentionedEntity("CypherSquad", "")),
        claims=claims,
    )
    pieces = split_independent_claims(fragment)
    assert len(pieces) == 2
    assert [piece.entities[0].surface for piece in pieces] == ["Plasma", "CypherSquad"]


def test_financial_flow_table_remains_one_fragment():
    from astrafeed.application.agenda_extract import split_independent_claims
    from astrafeed.domain.agenda import Claim, Fragment, MentionedEntity

    text = "Финпотоки ETF за вчера:\nBTC = +$100.\nETH = +$50."
    claims = (
        Claim("event", "author", "BTC = +$100.", 26, 38),
        Claim("event", "author", "ETH = +$50.", 39, 50),
    )
    fragment = Fragment(
        text=text,
        start=0,
        end=len(text),
        entities=(MentionedEntity("BTC", ""), MentionedEntity("ETH", "")),
        claims=claims,
    )
    assert split_independent_claims(fragment) == (fragment,)

class RecordingExtractor:
    def __init__(self, draft: ExtractionResult | Exception) -> None:
        self.draft = draft
        self.calls: list[str] = []

    async def extract(self, text: str) -> ExtractionResult:
        self.calls.append(text)
        if isinstance(self.draft, Exception):
            raise self.draft
        return self.draft


def _pub(
    text: str,
    *,
    source_id: int = 1,
    external_id: str = "10",
    channel: str = "@alpha",
    published: datetime | None = None,
    detected: datetime | None = None,
    version: int = 1,
) -> PublicationVersion:
    published = published or datetime(2026, 9, 23, 12, tzinfo=UTC)
    return PublicationVersion(
        publication_id=publication_id(source_id, external_id),
        source_id=source_id,
        external_id=external_id,
        text=text,
        text_hash=text_hash(text),
        published_at=published,
        detected_at=detected or published,
        channel_ref=channel,
        link=f"https://t.me/{channel[1:]}/{external_id}",
        version=version,
    )


def _result(text: str, fragments: tuple[Fragment, ...], status: str = "ok") -> ExtractionResult:
    digest = text_hash(text)
    return ExtractionResult(
        reuse_key=analysis_reuse_key(digest),
        text_hash=digest,
        classifier_version=CLASSIFIER_VERSION,
        status=status,  # type: ignore[arg-type]
        fragments=fragments,
    )


@pytest.mark.asyncio
async def test_same_text_is_extracted_once_and_kept_for_each_location():
    text = "SEC одобрила спотовый ETH ETF. Это событие."
    fragment = Fragment(
        text=text,
        start=0,
        end=len(text),
        entities=(MentionedEntity("ETH ETF", "спотовый ETH ETF"),),
        claims=(
            Claim(
                kind="event",
                speaker="author",
                quote="SEC одобрила спотовый ETH ETF.",
                start=0,
                end=30,
            ),
        ),
    )
    extractor = RecordingExtractor(_result(text, (fragment,)))
    store = InMemoryAgendaStore()
    first = _pub(text, source_id=1, external_id="10", channel="@alpha")
    second = _pub(text, source_id=2, external_id="7", channel="@beta")
    await store.record_publication(first)
    await store.record_publication(second)

    a = await analyze_publication(store, extractor, first)
    b = await analyze_publication(store, extractor, second)

    assert a.status == "ok" and b.status == "ok"
    assert extractor.calls == [text]
    assert len(store.locations_for_hash(first.text_hash)) == 2


@pytest.mark.asyncio
async def test_unverified_claim_is_dropped_empty_differs_from_error():
    text = "Цена биткоина выросла."
    bad = Fragment(
        text=text,
        start=0,
        end=len(text),
        claims=(
            Claim(
                kind="event",
                speaker="author",
                quote="выросла до 200 тысяч",
                start=0,
                end=5,
            ),
        ),
    )
    store = InMemoryAgendaStore()
    pub = _pub(text)
    await store.record_publication(pub)
    empty_ok = await analyze_publication(store, RecordingExtractor(_result(text, (bad,))), pub)
    assert empty_ok.status == "empty"
    assert empty_ok.fragments[0].claims == ()

    failing = RecordingExtractor(RuntimeError("llm down"))
    other = _pub("Другой пост без цитаты.", external_id="11")
    await store.record_publication(other)
    errored = await analyze_publication(store, failing, other)
    assert errored.status == "error"
    assert store.queue_reason(other.publication_id) == "extract_error"


@pytest.mark.asyncio
async def test_ad_fragment_does_not_drop_the_rest_of_the_post():
    text = "Реклама: купи курс. Затем SEC одобрила спотовый ETH ETF."
    fragments = (
        Fragment(
            text="Реклама: купи курс.",
            start=0,
            end=19,
            is_ad=True,
            claims=(
                Claim(
                    kind="explicit_call",
                    speaker="author",
                    quote="купи курс",
                    start=9,
                    end=18,
                    is_ad=True,
                ),
            ),
        ),
        Fragment(
            text="Затем SEC одобрила спотовый ETH ETF.",
            start=20,
            end=len(text),
            claims=(
                Claim(
                    kind="event",
                    speaker="author",
                    quote="SEC одобрила спотовый ETH ETF.",
                    start=26,
                    end=56,
                ),
            ),
        ),
    )
    store = InMemoryAgendaStore()
    pub = _pub(text)
    await store.record_publication(pub)
    result = await analyze_publication(store, RecordingExtractor(_result(text, fragments)), pub)
    assert result.status == "ok"
    assert result.fragments[0].is_ad is True
    assert result.fragments[1].claims[0].kind == "event"


@pytest.mark.asyncio
async def test_relative_dates_resolve_per_instance_and_edit_makes_new_version():
    text = "Сегодня отток ETH ETF. Вчера приток."
    fragment = Fragment(
        text=text,
        start=0,
        end=len(text),
        claims=(
            Claim(
                kind="event",
                speaker="author",
                quote="Сегодня отток ETH ETF.",
                start=0,
                end=22,
                dates=("сегодня",),
            ),
        ),
    )
    store = InMemoryAgendaStore()
    extractor = RecordingExtractor(_result(text, (fragment,)))
    monday = _pub(
        text,
        published=datetime(2026, 9, 21, 10, tzinfo=UTC),
        external_id="1",
    )
    tuesday = _pub(
        text,
        source_id=2,
        external_id="2",
        channel="@beta",
        published=datetime(2026, 9, 22, 10, tzinfo=UTC),
    )
    await store.record_publication(monday)
    await store.record_publication(tuesday)
    a = await analyze_publication(store, extractor, monday)
    b = await analyze_publication(store, extractor, tuesday)
    assert a.fragments[0].claims[0].dates == ("2026-09-21",)
    assert b.fragments[0].claims[0].dates == ("2026-09-22",)
    assert extractor.calls == [text]

    edited_text = "Сегодня отток ETH ETF. Правка: цифра $80 млн."
    edited = _pub(
        edited_text,
        external_id="1",
        published=monday.published_at,
        detected=datetime(2026, 9, 21, 18, tzinfo=UTC),
        version=2,
    )
    previous = await store.record_publication(edited)
    assert previous is not None and previous.version == 1
    assert store.latest_version("1:1").version == 2
