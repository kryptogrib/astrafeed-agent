import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.llm.agenda import Assignment
from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.application.agenda_cycle import cycle_health, run_cycle
from astrafeed.domain.agenda import (
    CLASSIFIER_VERSION,
    Claim,
    ExtractionResult,
    Fragment,
    MentionedEntity,
    analysis_reuse_key,
    text_hash,
)
from astrafeed.domain.ingestion import Coverage
from astrafeed.domain.models import Item as SourceItem
from astrafeed.domain.spend_budget import BudgetExceeded


def _item(source: str, external: str, text: str, when: datetime) -> SourceItem:
    return SourceItem(
        channel_ref=source,
        external_id=external,
        text=text,
        link=f"https://t.me/{source[1:]}/{external}",
        timestamp=when,
        channel_name=source,
    )


class Reader:
    def __init__(self, items: dict[int, list[SourceItem]], complete: bool = True) -> None:
        self.items = items
        self.complete = complete

    async def read_window(self, source_id, start, end):
        return [i for i in self.items.get(source_id, []) if start <= i.timestamp < end]

    async def coverage(self, source_id, start, end):
        return Coverage(start=start, end=end, complete=self.complete)


class Extractor:
    async def extract(self, text: str) -> ExtractionResult:
        quote = text
        return ExtractionResult(
            reuse_key=analysis_reuse_key(text_hash(text)),
            text_hash=text_hash(text),
            classifier_version=CLASSIFIER_VERSION,
            status="ok",
            fragments=(
                Fragment(
                    text=text,
                    start=0,
                    end=len(text),
                    entities=(MentionedEntity("ETH", text),),
                    claims=(
                        Claim(
                            kind="event",
                            speaker="author",
                            quote=quote,
                            start=0,
                            end=len(quote),
                        ),
                    ),
                ),
            ),
        )


class Embedder:
    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class Assigner:
    async def assign(self, **kwargs):
        stories = kwargs["stories"]
        return Assignment(
            entity_decisions=(("ETH", "new", None, "Ethereum"),),
            story_decision="existing" if stories else "new",
            story_id=stories[0].story_id if stories else None,
            title_ru="Потоки ETH ETF",
            boundary="ETF",
            event_decision="new",
            event_id=None,
            paraphrase_ru="Пишут про ETH",
        )


@pytest.mark.asyncio
async def test_cycle_publishes_snapshot_and_restart_does_not_duplicate():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)
    start = t - timedelta(hours=10)
    reader = Reader(
        {
            1: [_item("@a", "1", "Отток ETH ETF 120 млн сегодня.", start + timedelta(hours=1))],
            2: [_item("@b", "2", "BlackRock: отток ETH ETF 120 млн.", start + timedelta(hours=2))],
        }
    )
    snap = await run_cycle(
        store,
        reader=reader,
        source_ids=[1, 2],
        extractor=Extractor(),
        embedder=Embedder(),
        assigner=Assigner(),
        now=t,
    )
    assert snap is not None
    assert snap.agenda
    first_id = snap.snapshot_id
    links = await store.links_for_publications({"1:1", "2:2"})
    assert len(links) == 2

    again = await run_cycle(
        store,
        reader=reader,
        source_ids=[1, 2],
        extractor=Extractor(),
        embedder=Embedder(),
        assigner=Assigner(),
        now=t + timedelta(minutes=5),
    )
    assert again is not None
    assert again.snapshot_id != first_id
    links = await store.links_for_publications({"1:1", "2:2"})
    assert len(links) == 2


@pytest.mark.asyncio
async def test_extraction_overlaps_but_assignment_stays_chronological():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)
    texts = [f"Отток ETH ETF номер {number} сегодня." for number in range(3)]

    class ConcurrentExtractor(Extractor):
        active = 0
        maximum = 0

        async def extract(self, text):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return await super().extract(text)

    class RecordingAssigner(Assigner):
        def __init__(self):
            self.order = []

        async def assign(self, **kwargs):
            self.order.append(kwargs["fragment"].text)
            return await super().assign(**kwargs)

    extractor = ConcurrentExtractor()
    assigner = RecordingAssigner()
    await run_cycle(
        store,
        reader=Reader(
            {
                1: [
                    _item("@a", str(index), text, t - timedelta(hours=3 - index))
                    for index, text in enumerate(texts)
                ]
            }
        ),
        source_ids=[1],
        extractor=extractor,
        embedder=Embedder(),
        assigner=assigner,
        now=t,
        extract_concurrency=2,
    )

    assert extractor.maximum == 2
    assert assigner.order == texts


@pytest.mark.asyncio
async def test_concurrent_extraction_reuses_identical_text():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)
    quote = "Отток ETH ETF составил 120 млн сегодня."

    class CountingExtractor(Extractor):
        calls = 0

        async def extract(self, text):
            self.calls += 1
            await asyncio.sleep(0.01)
            return await super().extract(text)

    extractor = CountingExtractor()
    await run_cycle(
        store,
        reader=Reader(
            {
                1: [_item("@a", "1", quote, t - timedelta(hours=2))],
                2: [_item("@b", "2", quote, t - timedelta(hours=1))],
            }
        ),
        source_ids=[1, 2],
        extractor=extractor,
        embedder=Embedder(),
        assigner=Assigner(),
        now=t,
        extract_concurrency=2,
    )

    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_extraction_budget_block_preserves_last_snapshot():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)
    initial = await run_cycle(
        store,
        reader=Reader(
            {1: [_item("@a", "1", "Отток ETH ETF сегодня утром.", t - timedelta(hours=2))]}
        ),
        source_ids=[1],
        extractor=Extractor(),
        embedder=Embedder(),
        assigner=Assigner(),
        now=t,
    )
    assert initial is not None

    class BlockedExtractor:
        async def extract(self, text):
            raise BudgetExceeded("Daily global LLM budget exhausted")

    blocked = await run_cycle(
        store,
        reader=Reader(
            {
                1: [
                    _item("@a", "1", "Отток ETH ETF сегодня утром.", t - timedelta(hours=2)),
                    _item(
                        "@a", "2", "Новый отток ETH ETF сегодня вечером.", t - timedelta(hours=1)
                    ),
                ]
            }
        ),
        source_ids=[1],
        extractor=BlockedExtractor(),
        embedder=Embedder(),
        assigner=Assigner(),
        now=t + timedelta(minutes=5),
        extract_concurrency=2,
    )

    assert blocked is None
    assert (await store.get_snapshot(None)).snapshot_id == initial.snapshot_id
    assert store.queue_reason("1:2") == "new"
    assert (await store.get_cycle_state()).budget_blocked is True


@pytest.mark.asyncio
async def test_collection_can_cover_72_hours_without_changing_comparison_windows():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)
    old = _item("@a", "1", "Старый сюжет ETH ETF сегодня утром.", t - timedelta(hours=60))
    recent = _item("@a", "2", "Новый сюжет ETH ETF сегодня утром.", t - timedelta(hours=1))
    collected = []

    async def collect(start, end):
        collected.append((start, end))

    snapshot = await run_cycle(
        store,
        reader=Reader({1: [old, recent]}),
        source_ids=[1],
        extractor=Extractor(),
        embedder=Embedder(),
        assigner=Assigner(),
        now=t,
        collect=collect,
        collection_window=timedelta(hours=72),
    )

    assert collected == [(t - timedelta(hours=72), t)]
    assert await store.latest_publication("1:1") is not None
    assert snapshot.coverage.publications_total == 1


@pytest.mark.asyncio
async def test_budget_block_keeps_last_snapshot_and_queue():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)
    start = t - timedelta(hours=10)

    class BlockingEmbedder:
        async def embed(self, texts):
            raise BudgetExceeded("Daily global LLM budget exhausted")

    first = await run_cycle(
        store,
        reader=Reader(
            {
                1: [_item("@a", "1", "Отток ETH ETF 120 млн сегодня.", start)],
                2: [_item("@b", "2", "Повтор оттока ETH ETF.", start + timedelta(hours=1))],
            }
        ),
        source_ids=[1, 2],
        extractor=Extractor(),
        embedder=Embedder(),
        assigner=Assigner(),
        now=t,
    )
    assert first is not None
    blocked = await run_cycle(
        store,
        reader=Reader(
            {
                1: [_item("@a", "1", "Отток ETH ETF 120 млн сегодня.", start)],
                2: [_item("@b", "3", "Новый пост про ETH ETF вечером.", t - timedelta(hours=1))],
            }
        ),
        source_ids=[1, 2],
        extractor=Extractor(),
        embedder=BlockingEmbedder(),
        assigner=Assigner(),
        now=t + timedelta(minutes=5),
    )
    assert blocked is None
    latest = await store.get_snapshot(None)
    assert latest is not None and latest.snapshot_id == first.snapshot_id
    state = await store.get_cycle_state()
    assert state.budget_blocked is True
    assert await store.queue_depth() >= 1


@pytest.mark.asyncio
async def test_provider_error_detail_does_not_leak_into_cycle_health():
    store = InMemoryAgendaStore()
    t = datetime(2026, 9, 24, 12, tzinfo=UTC)

    class LeakyAssigner:
        async def assign(self, **kwargs):
            raise RuntimeError("SECRET_POST_CONTENT: full provider completion")

    await run_cycle(
        store,
        reader=Reader({1: [_item("@a", "1", "Отток ETH ETF сегодня.", t - timedelta(hours=1))]}),
        source_ids=[1],
        extractor=Extractor(),
        embedder=Embedder(),
        assigner=LeakyAssigner(),
        now=t,
    )

    state = await store.get_cycle_state()
    assert state.last_error == ""
    assert "SECRET_POST_CONTENT" not in state.last_error
    assert store.queue_reason("1:1") == "assign_error"


@pytest.mark.asyncio
async def test_health_redacts_legacy_persisted_provider_error():
    store = InMemoryAgendaStore()
    state = await store.get_cycle_state()
    state.last_error = "<failed_attempts>\nSECRET_POST_CONTENT: full completion\n</failed_attempts>"
    await store.set_cycle_state(state)

    payload = await cycle_health(store, now=datetime(2026, 9, 24, 12, tzinfo=UTC), commit="test")

    assert payload["cycle"]["last_error"] == "analysis_error"
    assert "SECRET_POST_CONTENT" not in str(payload)
