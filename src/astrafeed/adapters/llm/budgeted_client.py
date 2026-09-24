"""Gate every completion, including Instructor repairs and research retries."""

import asyncio
import math
from contextlib import suppress
from types import SimpleNamespace
from typing import Any

from astrafeed.ports.spend_budget import SpendBudget


class BudgetedClient:
    def __init__(
        self,
        client: Any,
        *,
        store: SpendBudget,
        user_id: int,
        reservation_amount: float = 0.5,
        max_tokens: int = 8192,
    ) -> None:
        if not math.isfinite(reservation_amount) or reservation_amount <= 0:
            raise ValueError("Reservation must be finite and positive")
        if max_tokens <= 0:
            raise ValueError("Token ceiling must be positive")
        # SDK-internal retries bypass create(); disable them at this boundary.
        self._client = client.with_options(max_retries=0)
        self._store = store
        self._user_id = user_id
        self._reservation_amount = reservation_amount
        self._max_tokens = max_tokens
        self.chat = SimpleNamespace(completions=self)
        self.embeddings = SimpleNamespace(create=self.create_embeddings)

    def with_options(self, **kwargs: Any) -> "BudgetedClient":
        return BudgetedClient(
            self._client.with_options(**{**kwargs, "max_retries": 0}),
            store=self._store,
            user_id=self._user_id,
            reservation_amount=self._reservation_amount,
            max_tokens=self._max_tokens,
        )

    async def create(self, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            raise ValueError("Budgeted streaming is not supported")
        token_key = "max_completion_tokens" if "max_completion_tokens" in kwargs else "max_tokens"
        kwargs[token_key] = min(kwargs.get(token_key) or self._max_tokens, self._max_tokens)
        extra_body = dict(kwargs.get("extra_body") or {})
        extra_body["usage"] = {"include": True}
        kwargs["extra_body"] = extra_body
        reservation = await self._store.reserve(self._user_id, self._reservation_amount)
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except BaseException as exc:
            await self._record_failure(reservation, exc)
            raise
        await self._settle(reservation, response)
        return response

    async def create_embeddings(self, **kwargs: Any) -> Any:
        extra_body = dict(kwargs.get("extra_body") or {})
        extra_body["usage"] = {"include": True}
        kwargs["extra_body"] = extra_body
        reservation = await self._store.reserve(self._user_id, self._reservation_amount)
        try:
            response = await self._client.embeddings.create(**kwargs)
        except BaseException as exc:
            await self._record_failure(reservation, exc)
            raise
        await self._settle(reservation, response)
        return response

    async def _record_failure(self, reservation: str, exc: BaseException) -> None:
        outcome = (
            "cancelled" if isinstance(exc, asyncio.CancelledError)
            else "timeout" if isinstance(exc, TimeoutError)
            else "error"
        )
        with suppress(Exception):
            await self._store.fail(reservation, outcome)

    async def _settle(self, reservation: str, response: Any) -> None:
        cost = getattr(getattr(response, "usage", None), "cost", None)
        if cost is None:
            await self._store.fail(reservation, "missing_usage")
            return
        try:
            actual_cost = float(cost)
        except (TypeError, ValueError):
            await self._store.fail(reservation, "missing_usage")
            return
        if math.isfinite(actual_cost) and actual_cost >= 0:
            await self._store.settle(reservation, actual_cost)
        else:
            await self._store.fail(reservation, "missing_usage")
