import pytest

from astrafeed.prefilter.dedup import Deduper
from tests.conftest import make_item


@pytest.mark.asyncio
async def test_exact_text_duplicate_collapses():
    d = Deduper()
    items = [make_item("1", "Binance lists FOO token"), make_item("2", "Binance lists FOO token")]
    out = await d.filter(items)
    assert [i.external_id for i in out] == ["1"]


@pytest.mark.asyncio
async def test_same_url_collapses():
    d = Deduper()
    a = make_item("1", "see https://x.com/a here")
    b = make_item("2", "different words https://x.com/a end")
    out = await d.filter([a, b])
    assert [i.external_id for i in out] == ["1"]


@pytest.mark.asyncio
async def test_distinct_text_kept():
    d = Deduper()
    items = [make_item("1", "Apple earnings up"), make_item("2", "Tesla recall news")]
    assert len(await d.filter(items)) == 2


@pytest.mark.asyncio
async def test_persists_across_calls():
    d = Deduper()
    await d.filter([make_item("1", "repeated story text here")])
    out = await d.filter([make_item("2", "repeated story text here")])
    assert out == []  # reprint in a later tick is dropped
