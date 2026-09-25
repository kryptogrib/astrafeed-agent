import asyncio
from types import SimpleNamespace

import pytest

from astrafeed.adapters.llm.budgeted_client import BudgetedClient
from astrafeed.domain.spend_budget import BudgetExceeded


class Budget:
    def __init__(self, *, exhausted: bool = False):
        self.exhausted = exhausted
        self.calls = []

    async def reserve(self, user_id, amount):
        self.calls.append(("reserve", user_id, amount))
        if self.exhausted:
            raise BudgetExceeded("daily limit")
        return "reservation"

    async def settle(self, reservation, cost):
        self.calls.append(("settle", reservation, cost))

    async def fail(self, reservation, outcome):
        self.calls.append(("fail", reservation, outcome))


class OpenAI:
    def __init__(self, result=None, error=None):
        self.calls = 0
        self.kwargs = None
        self.result = result
        self.error = error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.embeddings = SimpleNamespace(create=self.create)

    def with_options(self, **kwargs):
        return self

    async def create(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_chat_create_reserves_caps_tokens_and_settles_reported_cost():
    budget = Budget()
    openai = OpenAI(SimpleNamespace(usage=SimpleNamespace(cost=0.03)))
    client = BudgetedClient(openai, store=budget, user_id=9, max_tokens=100)

    await client.chat.completions.create(model="m", max_tokens=1000, messages=[])

    assert openai.kwargs["max_tokens"] == 100
    assert openai.kwargs["extra_body"]["usage"] == {"include": True}
    assert budget.calls == [("reserve", 9, 0.5), ("settle", "reservation", 0.03)]


@pytest.mark.asyncio
async def test_streaming_is_rejected_before_reserving():
    budget, openai = Budget(), OpenAI()
    client = BudgetedClient(openai, store=budget, user_id=0)
    with pytest.raises(ValueError, match="streaming"):
        await client.chat.completions.create(model="m", stream=True)
    assert budget.calls == []
    assert openai.calls == 0


@pytest.mark.asyncio
async def test_exhausted_budget_does_not_call_chat_client():
    budget, openai = Budget(exhausted=True), OpenAI()
    client = BudgetedClient(openai, store=budget, user_id=0)
    with pytest.raises(BudgetExceeded):
        await client.chat.completions.create(model="m")
    assert openai.calls == 0


@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (TimeoutError(), "timeout"),
        (asyncio.CancelledError(), "cancelled"),
        (RuntimeError("provider"), "error"),
    ],
)
@pytest.mark.asyncio
async def test_chat_failure_records_outcome_and_propagates(error, outcome):
    budget, openai = Budget(), OpenAI(error=error)
    client = BudgetedClient(openai, store=budget, user_id=0)
    with pytest.raises(type(error)):
        await client.chat.completions.create(model="m")
    assert budget.calls[-1] == ("fail", "reservation", outcome)


@pytest.mark.parametrize("cost", [None, "not-a-number"])
@pytest.mark.asyncio
async def test_missing_or_non_numeric_usage_keeps_unknown_charge(cost):
    budget = Budget()
    openai = OpenAI(SimpleNamespace(usage=SimpleNamespace(cost=cost)))
    client = BudgetedClient(openai, store=budget, user_id=0)
    await client.chat.completions.create(model="m")
    assert budget.calls[-1] == ("fail", "reservation", "missing_usage")


@pytest.mark.parametrize(("reservation", "max_tokens"), [(0, 10), (float("nan"), 10), (0.5, 0)])
def test_constructor_rejects_invalid_limits(reservation, max_tokens):
    with pytest.raises(ValueError):
        BudgetedClient(
            OpenAI(),
            store=Budget(),
            user_id=0,
            reservation_amount=reservation,
            max_tokens=max_tokens,
        )
