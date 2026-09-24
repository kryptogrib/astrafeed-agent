import httpx
import pytest

from astrafeed.adapters.http.app import create_app


def fake_news_pulse(topic: str, window: str) -> dict:
    if window == "bad":
        raise ValueError("window must be YYYY-MM-DD..YYYY-MM-DD")
    if topic == "missing":
        raise LookupError("news pulse is not cached")
    return {
        "topic": topic,
        "window": {"requested": window},
        "brief_markdown": "# News Pulse\n",
    }


async def get(app, url):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(url)


@pytest.mark.asyncio
async def test_news_pulse_is_absent_without_provider():
    url = "/news-pulse?topic=zec&window=2026-09-17..2026-09-19"
    assert (await get(create_app(), url)).status_code == 404


@pytest.mark.asyncio
async def test_news_pulse_json_and_markdown():
    app = create_app(news_pulse=fake_news_pulse)
    r = await get(app, "/news-pulse?topic=zec&window=2026-09-17..2026-09-19")
    assert r.status_code == 200
    assert r.json()["window"] == {"requested": "2026-09-17..2026-09-19"}
    r = await get(app, "/news-pulse?topic=zec&window=2026-09-17..2026-09-19&format=md")
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.text == "# News Pulse\n"


@pytest.mark.asyncio
async def test_news_pulse_errors_and_does_not_replace_pulse():
    app = create_app(news_pulse=fake_news_pulse)
    assert (await get(app, "/news-pulse?topic=zec&window=bad")).status_code == 422
    missing = "/news-pulse?topic=missing&window=2026-09-17..2026-09-19"
    assert (await get(app, missing)).status_code == 404
    assert (await get(app, "/pulse?topic=zec")).status_code == 404
