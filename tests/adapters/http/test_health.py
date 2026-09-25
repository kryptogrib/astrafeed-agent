import httpx
import pytest

from astrafeed.adapters.http.app import create_app


@pytest.mark.asyncio
async def test_health_endpoint_is_live():
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_live_and_ready_health_endpoints_are_distinct():
    app = create_app(health=lambda: {"status": "degraded", "reason": "telegram_auth_key"})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/healthz/live")
        ready = await client.get("/healthz/ready")
        legacy = await client.get("/healthz")
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.json()["reason"] == "telegram_auth_key"
    assert legacy.status_code == 200
    assert legacy.json()["status"] == "degraded"
