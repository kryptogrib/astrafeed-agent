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
