import json
from datetime import UTC, datetime

import httpx
import pytest

from astrafeed.adapters.llm.jev import JevEvidenceVerifier
from astrafeed.domain.agenda import Story


def _story() -> Story:
    return Story(
        story_id="s1",
        title_ru="Binance листит HYPE",
        boundary="Листинг HYPE на Binance",
        first_seen=datetime(2026, 9, 24, tzinfo=UTC),
    )


def _verifier(handler, **kwargs) -> JevEvidenceVerifier:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return JevEvidenceVerifier(client, api_key="k", **kwargs)


@pytest.mark.asyncio
async def test_each_quote_gets_its_own_noul_decision_and_threshold():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append((request, body))
        noul = 0.9 if "Binance" in body["state"]["quote"] else 0.2
        return httpx.Response(200, json={"answers": {"supported": {"type": "noul", "noul": noul}}})

    verdicts = await _verifier(handler).verify(_story(), ["Binance листит HYPE", "Payy взломан"])

    assert verdicts == [True, False]
    request, body = requests[0]
    assert request.url == "https://openrouter.ai/api/alpha/decisions"
    assert request.headers["authorization"] == "Bearer k"
    assert body["model"] == "typesafe/jev-1.13"
    assert body["state"]["story"] == {
        "title": "Binance листит HYPE",
        "boundary": "Листинг HYPE на Binance",
    }
    assert body["questions"]["supported"]["type"] == "noul"


@pytest.mark.asyncio
async def test_threshold_is_strict_so_even_odds_reject():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answers": {"supported": {"type": "noul", "noul": 0.5}}})

    assert await _verifier(handler).verify(_story(), ["q"]) == [False]
    assert await _verifier(handler, threshold=0.4).verify(_story(), ["q"]) == [True]


@pytest.mark.asyncio
async def test_missing_answer_fails_instead_of_guessing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answers": {}})

    with pytest.raises(ValueError):
        await _verifier(handler).verify(_story(), ["q"])


@pytest.mark.asyncio
async def test_http_errors_surface():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(529, json={"error": "overloaded"})

    with pytest.raises(httpx.HTTPStatusError):
        await _verifier(handler).verify(_story(), ["q"])
