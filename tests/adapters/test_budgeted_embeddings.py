from types import SimpleNamespace

import pytest

from astrafeed.adapters.llm.budgeted_client import BudgetedClient
from astrafeed.domain.spend_budget import BudgetExceeded


class FakeBudget:
    def __init__(self, limit: float = 5.0) -> None:
        self.limit = limit
        self.used = 0.0
        self.reservations: dict[str, float] = {}
        self.n = 0

    async def reserve(self, user_id: int, amount: float) -> str:
        if self.used + amount > self.limit:
            raise BudgetExceeded("Daily global LLM budget exhausted")
        self.n += 1
        key = f"r{self.n}"
        self.reservations[key] = amount
        self.used += amount
        return key

    async def settle(self, reservation_id: str, actual_cost: float) -> None:
        previous = self.reservations[reservation_id]
        self.used += actual_cost - previous
        self.reservations[reservation_id] = actual_cost

    async def fail(self, reservation_id: str, outcome: str) -> None:
        self.outcome = outcome


class FakeOpenAI:
    def __init__(self) -> None:
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._unused))
        self.embeddings = SimpleNamespace(create=self._embed)

    def with_options(self, **kwargs):
        return self

    async def _unused(self, **kwargs):
        raise AssertionError("chat should not run")

    async def _embed(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])],
            usage=SimpleNamespace(cost=0.01),
        )


@pytest.mark.asyncio
async def test_embeddings_go_through_the_same_daily_budget():
    budget = FakeBudget(limit=0.4)
    client = BudgetedClient(FakeOpenAI(), store=budget, user_id=0, reservation_amount=0.5)
    with pytest.raises(BudgetExceeded):
        await client.embeddings.create(model="openai/text-embedding-3-small", input="x")

    budget = FakeBudget(limit=1.0)
    openai = FakeOpenAI()
    client = BudgetedClient(openai, store=budget, user_id=0, reservation_amount=0.5)
    response = await client.embeddings.create(
        model="openai/text-embedding-3-small", input=["hello"]
    )
    assert response.data[0].embedding == [0.1, 0.2]
    assert openai.calls == 1
    assert budget.used == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_timeout_keeps_charge_and_records_outcome():
    budget = FakeBudget()
    openai = FakeOpenAI()

    async def timeout(**kwargs):
        raise TimeoutError("provider deadline")

    openai.embeddings.create = timeout
    client = BudgetedClient(openai, store=budget, user_id=0, reservation_amount=0.5)
    with pytest.raises(TimeoutError):
        await client.embeddings.create(model="embedding", input="text")
    assert budget.used == 0.5
    assert budget.outcome == "timeout"
