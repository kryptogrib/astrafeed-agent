from datetime import UTC, datetime

import httpx
import pytest

from astrafeed.adapters.http.app import create_app
from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.application.agenda_query import (
    AgendaPreparing,
    agenda_payload,
    search_payload,
    story_payload,
)
from astrafeed.application.agenda_snapshot import publish_snapshot
from tests.adapters.http.test_agenda import _snapshot

T = datetime(2026, 9, 24, 12, tzinfo=UTC)


async def _app():
    store = InMemoryAgendaStore()
    await publish_snapshot(store, _snapshot(T))

    async def agenda(snapshot_id=None):
        return await agenda_payload(store, snapshot_id=snapshot_id, now=T)

    async def search(q, snapshot_id=None, limit=10, offset=0):
        return await search_payload(
            store, q, snapshot_id=snapshot_id, now=T, limit=limit, offset=offset
        )

    async def story(story_id, snapshot_id=None):
        return await story_payload(store, story_id, snapshot_id=snapshot_id, now=T)

    return create_app(agenda=agenda, stories_search=search, story=story)


async def _post(app, url: str, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(url, **kwargs)


async def test_bare_post_returns_agenda_for_okx_self_check():
    # OKX A2MCP review runs `curl -i -X POST <endpoint>` with no body and expects 200.
    r = await _post(await _app(), "/a2mcp/astrafeed")
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "agenda"
    assert body["usage"]["actions"]["agenda"].startswith("Empty body")
    assert "listing_status" not in body["usage"]
    assert body["preview"]["snapshot_id"] == "snap-demo"
    assert body["preview"]["stories"][0]["title"] == "Потоки ETH ETF"
    assert body["result"]["snapshot_id"] == "snap-demo"
    assert body["result"]["stories"][0]["title"] == "Потоки ETH ETF"


async def test_get_tool_url_is_a_landing_page_not_405():
    transport = httpx.ASGITransport(app=await _app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get("/a2mcp/astrafeed")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "POST this URL" in page.text
    assert "Потоки ETH ETF" in page.text


async def test_search_then_story_on_the_same_snapshot():
    app = await _app()
    found = await _post(app, "/a2mcp/astrafeed", json={"query": "ETH"})
    assert found.json()["action"] == "search"
    hit = found.json()["result"]["hits"][0]
    assert hit["story_id"] == "st-eth"

    card = await _post(
        app,
        "/a2mcp/astrafeed",
        json={"story_id": hit["story_id"], "snapshot_id": found.json()["result"]["snapshot_id"]},
    )
    assert card.json()["action"] == "story"
    assert card.json()["result"]["story"]["publications"][0]["link"] == "https://t.me/alpha/10"


async def test_markdown_format_and_errors():
    app = await _app()
    md = await _post(app, "/a2mcp/astrafeed", json={"format": "md"})
    assert md.headers["content-type"].startswith("text/markdown")
    assert "Потоки ETH ETF" in md.text

    both = await _post(app, "/a2mcp/astrafeed", json={"query": "ETH", "story_id": "st-eth"})
    assert both.status_code == 422
    assert (await _post(app, "/a2mcp/astrafeed", json={"story_id": "nope"})).status_code == 404


async def test_preparing_stays_503():
    async def preparing(snapshot_id=None):
        raise AgendaPreparing("preparing")

    app = create_app(agenda=preparing, stories_search=preparing, story=preparing)
    r = await _post(app, "/a2mcp/astrafeed")
    assert r.status_code == 503
    assert r.json()["status"] == "preparing"


@pytest.mark.parametrize("path", ["/a2mcp/astrafeed"])
async def test_not_mounted_without_agenda(path):
    app = create_app(pulse=lambda topic, window=None: {"brief_markdown": "x"})
    assert (await _post(app, path)).status_code in (404, 405)
