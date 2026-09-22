from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.llm.stub import StubLLMClient
from astrafeed.adapters.source.fake import FakeSource
from astrafeed.application.brief import build_brief


@pytest.mark.asyncio
async def test_complete_window_returns_english_brief_markdown():
    result = await build_brief(
        FakeSource([]), StubLLMClient(), ["@crypto"], timedelta(hours=24), datetime.now(UTC)
    )
    assert result.coverage.complete
    assert "No significant items" in result.markdown


@pytest.mark.asyncio
async def test_truncated_window_reports_incomplete_coverage():
    source = FakeSource([])
    source.truncated = True
    result = await build_brief(
        source, StubLLMClient(), ["@crypto"], timedelta(hours=24), datetime.now(UTC)
    )
    assert result.coverage.truncated
    assert "INCOMPLETE" in result.markdown
    assert "No significant items" not in result.markdown


@pytest.mark.asyncio
async def test_brief_contains_scored_event_and_source_link():
    from astrafeed.domain import Item, Route, Verdict

    now = datetime.now(UTC)
    item = Item(
        channel_ref="@crypto",
        external_id="1",
        text="SOL added to a new market",
        link="https://t.me/crypto/1",
        timestamp=now - timedelta(minutes=2),
    )
    llm = StubLLMClient(
        {
            "1": Verdict(
                item=item, route=Route.REPORT, summary="SOL added to a new market", importance=5
            )
        }
    )
    result = await build_brief(FakeSource([item]), llm, ["@crypto"], timedelta(hours=24), now)
    assert "SOL added to a new market" in result.markdown
    assert "[SOL added to a new market](https://t.me/crypto/1)" in result.markdown


@pytest.mark.asyncio
async def test_source_error_is_visible_and_empty_window_is_not_called_empty():
    source = FakeSource([])
    source.errors = {"@crypto": "temporarily unavailable"}
    result = await build_brief(
        source, StubLLMClient(), ["@crypto"], timedelta(hours=24), datetime.now(UTC)
    )
    assert not result.coverage.complete
    assert "temporarily unavailable" in result.markdown
    assert "No significant items" not in result.markdown
