from dataclasses import replace
from functools import partial

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.http.app import create_app
from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.adapters.repository.sqlite.agenda import SqliteAgendaStore
from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.application.agenda_query import agenda_payload, search_payload, story_payload
from tests.application.test_agenda_changes import T, _pair


async def _app():
    before, after = _pair()
    store = InMemoryAgendaStore()
    await store.publish_snapshot(before)
    await store.publish_snapshot(after)

    async def search(q, **kwargs):
        return await search_payload(store, q, now=T, **kwargs)

    return create_app(
        agenda=partial(agenda_payload, store, now=T),
        stories_search=search,
        story=partial(story_payload, store, now=T),
    )


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_rest_and_a2mcp_return_pinned_deltas_and_full_fallbacks(method):
    app = await _app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def request(body):
            if method == "POST":
                response = await client.post("/a2mcp/astrafeed", json=body)
                data = response.json()
                return response, data.get("result", data)
            response = await client.get("/agenda", params=body)
            return response, response.json()

        response, data = await request({"since_snapshot_id": "snap-before"})
        assert response.status_code == 200
        assert data["snapshot_id"] == "snap-after"
        assert data["compared_to"] == "snap-before"
        assert data["stories"] == []
        assert data["changes"]["updated_stories"] == []

        response, data = await request({"since_snapshot_id": "expired"})
        assert response.status_code == 200
        assert data["comparison_status"] == "baseline_unavailable"
        assert data["stories"][0]["story_id"] == "st-eth"

        response, data = await request(
            {"snapshot_id": "snap-before", "since_snapshot_id": "snap-before"}
        )
        assert response.status_code == 200
        assert data["snapshot_id"] == "snap-before"
        assert data["stories"] == []

        for body, status in [
            ({"since_snapshot_id": " "}, 422),
            ({"snapshot_id": "snap-before", "since_snapshot_id": "snap-after"}, 422),
            ({"snapshot_id": "missing", "since_snapshot_id": "snap-before"}, 404),
        ]:
            response, _ = await request(body)
            assert response.status_code == status


@pytest.mark.parametrize("selector", [{"query": "ETH"}, {"story_id": "st-eth"}])
async def test_a2mcp_rejects_baseline_for_non_agenda_requests(selector):
    app = await _app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/a2mcp/astrafeed", json={**selector, "since_snapshot_id": "snap-before"}
        )
    assert response.status_code == 422
    assert "since_snapshot_id" in response.json()["detail"]


async def test_markdown_and_html_expose_comparison_and_keep_pinned_export_links():
    app = await _app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for format in ("md", "html"):
            response = await client.get(
                "/agenda", params={"since_snapshot_id": "snap-before", "format": format}
            )
            assert response.status_code == 200
            expected_cursor = r"snap\-before" if format == "md" else "snap-before"
            assert expected_cursor in response.text and "No changes" in response.text
            if format == "html":
                assert "snapshot_id=snap-after&amp;since_snapshot_id=snap-before" in response.text
        response = await client.post(
            "/a2mcp/astrafeed", json={"since_snapshot_id": "snap-before", "format": "md"}
        )
        assert "No changes" in response.text


async def test_sqlite_baseline_survives_restart_and_is_not_the_latest_snapshot(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'changes.db'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    store = SqliteAgendaStore(async_sessionmaker(engine, expire_on_commit=False))
    before, after = _pair()
    after = replace(after, agenda=())
    try:
        await store.publish_snapshot(before)
        await store.publish_snapshot(after)
    finally:
        await engine.dispose()

    engine = create_async_engine(url)
    store = SqliteAgendaStore(async_sessionmaker(engine, expire_on_commit=False))
    try:
        result = await agenda_payload(
            store, snapshot_id=None, since_snapshot_id="snap-before", now=T
        )
        assert result["snapshot_id"] == "snap-after"
        assert result["compared_to"] == "snap-before"
        assert result["changes"]["removed_stories"][0]["story_id"] == "st-eth"
        assert result["changes"]["new_stories"] == []
    finally:
        await engine.dispose()
