"""Audit observer hook on Deduper (testrun harness)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.conftest import make_item


@pytest.mark.asyncio
async def test_observer_records_in_tick_drop():
    from astrafeed.prefilter.dedup import Deduper

    events: list[dict] = []
    d = Deduper(observer=lambda **e: events.append(e))
    a = make_item("1", "same text")
    b = make_item("2", "same text")  # exact in-tick duplicate

    out = await d.filter([a, b])

    assert len(out) == 1
    dropped = [e for e in events if e["decision"] == "dropped"]
    assert len(dropped) == 1
    assert dropped[0]["scope"] == "in-tick"
    assert dropped[0]["item"].external_id == "2"
    assert dropped[0]["signature"]  # non-empty matched signature


@pytest.mark.asyncio
async def test_observer_records_kept_for_survivors():
    from astrafeed.prefilter.dedup import Deduper

    events: list[dict] = []
    d = Deduper(observer=lambda **e: events.append(e))
    a = make_item("1", "unique one")
    b = make_item("2", "unique two")

    await d.filter([a, b])

    kept = [e for e in events if e["decision"] == "kept"]
    assert {e["item"].external_id for e in kept} == {"1", "2"}
    assert all(e["scope"] is None for e in kept)


@pytest.mark.asyncio
async def test_observer_records_persistent_drop_scope():
    from astrafeed.adapters.repository.memory import InMemoryRepository
    from astrafeed.prefilter.dedup import Deduper, signatures_for

    repo = InMemoryRepository()
    item = make_item("1", "Binance lists FOO token")
    await repo.record_seen(signatures_for(item), item.timestamp)

    events: list[dict] = []
    d = Deduper(observer=lambda **e: events.append(e))
    since = item.timestamp - timedelta(days=7)
    out = await d.filter([item], repo=repo, since=since)

    assert out == []
    dropped = [e for e in events if e["decision"] == "dropped"]
    assert len(dropped) == 1
    assert dropped[0]["scope"] == "persistent"
    assert dropped[0]["item"].external_id == "1"


@pytest.mark.asyncio
async def test_observer_none_keeps_prod_behaviour():
    from astrafeed.prefilter.dedup import Deduper

    d = Deduper()  # no observer
    a = make_item("1", "same text")
    b = make_item("2", "same text")
    out = await d.filter([a, b])
    assert [i.external_id for i in out] == ["1"]
