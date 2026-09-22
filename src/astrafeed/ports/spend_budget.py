"""Durable reservations precede provider I/O; unknown outcomes remain charged."""

from typing import Protocol


class SpendBudget(Protocol):
    async def reserve(self, user_id: int, amount: float) -> str: ...

    async def settle(self, reservation_id: str, actual_cost: float) -> None: ...
