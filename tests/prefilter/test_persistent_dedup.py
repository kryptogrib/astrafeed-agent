"""Issue 15 — Persistent dedup: 7 acceptance criteria, one vertical slice each."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.conftest import make_item


# ---------------------------------------------------------------------------
# AC2 — first-seen item passes AND gets recorded
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac2_first_seen_passes_and_recorded():
    from astrafeed.adapters.repository.memory import InMemoryRepository
    from astrafeed.prefilter.dedup import Deduper, signatures_for

    repo = InMemoryRepository()
    item = make_item("1", "Apple earnings up 20 percent")
    d = Deduper()
    since = item.timestamp - timedelta(days=7)
    out = await d.filter([item], repo=repo, since=since)
    assert len(out) == 1
    # Verify it was recorded
    recorded = await repo.seen_signatures(signatures_for(item), since)
    assert recorded  # non-empty -> at least one sig recorded


# ---------------------------------------------------------------------------
# AC3 — same-URL duplicate filtered after restart (new Deduper, sig pre-seeded)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac3_same_url_filtered_after_restart():
    from astrafeed.adapters.repository.memory import InMemoryRepository
    from astrafeed.prefilter.dedup import Deduper

    repo = InMemoryRepository()
    url = "https://example.com/news/1"
    item_a = make_item("1", f"See {url} for details")
    item_b = make_item("2", f"Different text {url} same link")

    # Tick 1: item_a recorded
    d1 = Deduper()
    since = item_a.timestamp - timedelta(days=7)
    await d1.filter([item_a], repo=repo, since=since)

    # Tick 2: new Deduper (simulates restart), item_b shares URL -> filtered
    d2 = Deduper()
    out = await d2.filter([item_b], repo=repo, since=since)
    assert out == []


# ---------------------------------------------------------------------------
# AC4 — in-tick dedup preserved (identical items in same batch -> one survivor)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac4_in_tick_dedup_preserved():
    from astrafeed.adapters.repository.memory import InMemoryRepository
    from astrafeed.prefilter.dedup import Deduper

    repo = InMemoryRepository()
    item_a = make_item("1", "Binance lists FOO token")
    item_b = make_item("2", "Binance lists FOO token")  # exact duplicate
    d = Deduper()
    since = item_a.timestamp - timedelta(days=7)
    out = await d.filter([item_a, item_b], repo=repo, since=since)
    assert len(out) == 1
    assert out[0].external_id == "1"


# ---------------------------------------------------------------------------
# AC5 — dedup_window expiry: item whose record is older than window re-passes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac5_item_outside_window_not_filtered():
    from astrafeed.adapters.repository.memory import InMemoryRepository
    from astrafeed.prefilter.dedup import Deduper, signatures_for

    repo = InMemoryRepository()
    # Record it 8 days in the past (event-time)
    item = make_item("1", "Binance lists FOO token", hour=0)
    old_when = item.timestamp - timedelta(days=8)
    await repo.record_seen(signatures_for(item), old_when)

    # New item same text, window=7d -> since = timestamp - 7d, old record outside
    new_item = make_item("2", "Binance lists FOO token", hour=12)
    d = Deduper()
    since = new_item.timestamp - timedelta(days=7)
    out = await d.filter([new_item], repo=repo, since=since)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# AC7 — pipeline: cross-tick reprint is NOT scored (cost_log evidence)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac7_cross_tick_reprint_not_scored():
    from astrafeed.adapters.llm.stub import StubLLMClient
    from astrafeed.adapters.repository.memory import InMemoryRepository
    from astrafeed.adapters.source.fake import FakeSource
    from astrafeed.domain import Channel, Interest, Route, Verdict
    from astrafeed.pipeline.orchestrator import Pipeline
    from astrafeed.prefilter.dedup import DedupConfig

    item = make_item("1", "Binance lists FOO token")

    repo = InMemoryRepository()
    await repo.add_channel(Channel(telegram_ref="@c", name="C", id=None))
    await repo.set_global_interests([Interest("crypto listings")])

    def make_pipe():
        llm = StubLLMClient(
            route_for={item.external_id: Verdict(item=item, route=Route.REPORT, summary="A")}
        )
        return (
            Pipeline(
                source=FakeSource([item]),
                llm=llm,
                repo=repo,
                dedup_config=DedupConfig(window=timedelta(days=7)),
            ),
            llm,
        )

    # Tick 1: item passes, gets scored and recorded
    pipe1, llm1 = make_pipe()
    r1 = await pipe1.run_tick()
    assert r1.scored == 1
    assert llm1.score_calls == 1  # LLM was called

    # Tick 2: new Pipeline (fresh Deduper) same repo same item -> dedup hit
    pipe2, llm2 = make_pipe()
    r2 = await pipe2.run_tick()
    assert r2.scored == 0  # reprint filtered, never reached score()
    assert llm2.score_calls == 0  # LLM never called -> cost_log would show no new entry


# ---------------------------------------------------------------------------
# AC1 — reprint pre-seeded in repo is filtered before score()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_preseeded_sig_filtered():
    from astrafeed.adapters.repository.memory import InMemoryRepository
    from astrafeed.prefilter.dedup import Deduper, signatures_for

    repo = InMemoryRepository()
    item = make_item("1", "Binance lists FOO token")
    # Simulate prior tick: pre-seed repo
    await repo.record_seen(signatures_for(item), item.timestamp)

    d = Deduper()
    since = item.timestamp - timedelta(days=7)
    out = await d.filter([item], repo=repo, since=since)
    assert out == []
