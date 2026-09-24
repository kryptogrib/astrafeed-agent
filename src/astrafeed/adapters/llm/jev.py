"""Evidence verification on Jev, TypeSafe's decision model, via OpenRouter.

Jev answers typed questions with probabilities instead of generating text, so
a yes/no evidence check maps to one ``noul`` question per quote. Each quote is
judged in its own request: Jev evaluates a question against the whole state,
and sibling quotes would only add distracting context.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import httpx

from astrafeed.domain.agenda import Story

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"

_SUPPORTED = {
    "type": "noul",
    "instructions": (
        "Does `quote`, read on its own, clearly tie the main project or asset of "
        "`story` to the specific event, action or claim that `story.boundary` "
        "describes, with the same date, amount, participants and direction of action?"
    ),
    "criteria": {
        "true": (
            "The quote itself names the story's subject and states that exact event, "
            "action or claim."
        ),
        "false": (
            "The quote covers another event, another asset, background, a related "
            "topic, or has no clear subject; or its date, amount or participants differ."
        ),
    },
}


class JevEvidenceVerifier:
    def __init__(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        model: str = JEV_MODEL,
        threshold: float = 0.5,
    ) -> None:
        self._client = client
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model
        # Strict: at even odds the quote is rejected, matching "when in doubt, false".
        self._threshold = threshold

    async def verify(self, story: Story, quotes: Sequence[str]) -> list[bool]:
        async with asyncio.timeout(30):
            probabilities = await asyncio.gather(*(self._supported(story, q) for q in quotes))
        return [p > self._threshold for p in probabilities]

    async def _supported(self, story: Story, quote: str) -> float:
        response = await self._client.post(
            DECISIONS_URL,
            headers=self._headers,
            timeout=15,
            json={
                "model": self._model,
                "state": {
                    "story": {"title": story.title_ru, "boundary": story.boundary},
                    "quote": quote[:1000],
                },
                "questions": {"supported": _SUPPORTED},
            },
        )
        response.raise_for_status()
        answer = response.json().get("answers", {}).get("supported")
        if not isinstance(answer, dict) or not isinstance(answer.get("noul"), int | float):
            raise ValueError("Jev returned no evidence decision")
        return float(answer["noul"])
