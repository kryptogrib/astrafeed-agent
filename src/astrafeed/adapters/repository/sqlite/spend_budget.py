"""Atomic daily spend reservations in integer micro-dollars."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from astrafeed.adapters.repository.sqlite.models import SpendReservationRow
from astrafeed.domain.spend_budget import BudgetExceeded


def _micros(amount: float) -> int:
    value = Decimal(str(amount))
    if not value.is_finite() or value < 0:
        raise ValueError("Spend amount must be finite and nonnegative")
    return int((value * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


class SqliteSpendBudget:
    def __init__(
        self,
        session: async_sessionmaker,
        *,
        daily_limit: float = 5.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._limit = _micros(daily_limit)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def reserve(self, principal_id: int, amount: float) -> str:
        micros = _micros(amount)
        if micros <= 0:
            raise ValueError("Reservation must be positive")
        day = self._clock().astimezone(UTC).date().isoformat()
        reservation_id = uuid4().hex
        async with self._session() as session:
            # Serialize the read/check/write across workers and processes.
            await session.execute(text("BEGIN IMMEDIATE"))
            used = await session.scalar(
                select(func.coalesce(func.sum(SpendReservationRow.amount_micros), 0)).where(
                    SpendReservationRow.day == day,
                )
            )
            if int(used or 0) + micros > self._limit:
                raise BudgetExceeded("Daily global LLM budget exhausted")
            session.add(
                SpendReservationRow(
                    id=reservation_id,
                    principal_id=principal_id,
                    day=day,
                    amount_micros=micros,
                    settled=False,
                )
            )
            await session.commit()
        return reservation_id

    async def settle(self, reservation_id: str, actual_cost: float) -> None:
        micros = _micros(actual_cost)
        async with self._session() as session, session.begin():
            record = await session.get(SpendReservationRow, reservation_id)
            if record is None:
                raise LookupError("Unknown spend reservation")
            if record.settled:
                return
            record.amount_micros = micros
            record.settled = True
