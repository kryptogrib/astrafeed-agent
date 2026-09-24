import httpx
import pytest

from astrafeed.adapters.http.app import create_app


def fake_pulse(topic: str, window: str | None) -> dict:
    if topic != "zec":
        raise LookupError(f"no prepared slice for {topic!r}")
    if window == "bad":
        raise ValueError("window must be YYYY-MM-DD..YYYY-MM-DD")
    return {"topic": topic, "window": {"requested": window}, "brief_markdown": "# Pulse\n"}


async def get(app, url):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(url)


@pytest.mark.asyncio
async def test_pulse_is_absent_without_provider():
    assert (await get(create_app(), "/pulse?topic=zec")).status_code == 404


@pytest.mark.asyncio
async def test_pulse_json_and_markdown():
    app = create_app(pulse=fake_pulse)
    r = await get(app, "/pulse?topic=zec&window=2026-09-17..2026-09-19")
    assert r.status_code == 200
    assert r.json()["window"] == {"requested": "2026-09-17..2026-09-19"}
    r = await get(app, "/pulse?topic=zec&format=md")
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.text == "# Pulse\n"


@pytest.mark.asyncio
async def test_pulse_errors():
    app = create_app(pulse=fake_pulse)
    assert (await get(app, "/pulse?topic=sol")).status_code == 404
    assert (await get(app, "/pulse?topic=zec&window=bad")).status_code == 422


def fake_compare(topic: str, a: str, b: str) -> dict:
    if not a < b:
        raise ValueError("periods must not overlap")
    return {"topic": topic, "a": {"window": a}, "b": {"window": b}, "markdown": "# Compare\n"}


@pytest.mark.asyncio
async def test_compare_and_healthz_info():
    app = create_app(pulse=fake_pulse, compare=fake_compare, info={"commit": "abc", "db_ok": True})
    r = await get(app, "/pulse/compare?topic=zec&a=2026-09-17..2026-09-19&b=2026-09-20..2026-09-22")
    assert r.status_code == 200 and r.json()["b"] == {"window": "2026-09-20..2026-09-22"}
    r = await get(app, "/pulse/compare?topic=zec&a=x&b=x&format=md")
    assert r.status_code == 422
    assert (await get(app, "/healthz")).json() == {"status": "ok", "commit": "abc", "db_ok": True}
    no_compare = create_app(pulse=fake_pulse)
    assert (await get(no_compare, "/pulse/compare?topic=zec&a=1&b=2")).status_code == 404
