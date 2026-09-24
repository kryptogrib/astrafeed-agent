"""OKX public market data: spot price now and at a past minute. No API key."""

from __future__ import annotations

from datetime import datetime

import httpx

BASE_URL = "https://www.okx.com"


class OkxMarket:
    def __init__(self, *, timeout_seconds: float = 8.0, base_url: str = BASE_URL) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def _get(self, path: str, params: dict) -> list:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        body = response.json()
        if body.get("code") != "0":
            return []
        return body.get("data") or []

    async def last(self, inst_id: str) -> float | None:
        data = await self._get("/api/v5/market/ticker", {"instId": inst_id})
        return float(data[0]["last"]) if data else None

    async def open_at(self, inst_id: str, at: datetime) -> float | None:
        """Open of the one-minute candle containing ``at``."""
        minute_ms = int(at.timestamp() // 60 * 60_000)
        data = await self._get(
            "/api/v5/market/history-candles",
            {"instId": inst_id, "bar": "1m", "after": str(minute_ms + 60_000), "limit": "1"},
        )
        return float(data[0][1]) if data else None

    async def aclose(self) -> None:
        await self._client.aclose()
