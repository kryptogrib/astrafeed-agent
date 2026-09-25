"""Atomic daily spend reservations in integer micro-dollars."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from uuid import uuid4

from sqlalchemy import and_, case, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from astrafeed.adapters.repository.sqlite.models import SpendReservationRow
from astrafeed.domain.spend_budget import BudgetExceeded

UNKNOWN_RESERVATION_TTL = timedelta(minutes=15)


def _micros(amount: float) -> int:
    value = Decimal(str(amount))
    if not value.is_finite() or value < 0:
        raise ValueError("Spend amount must be finite and nonnegative")
    return int((value * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


async def migrate_spend_reservations(connection: AsyncConnection) -> None:
    columns = {
        row[1]
        for row in (await connection.exec_driver_sql("PRAGMA table_info(spend_reservation)")).all()
    }
    if "created_at" not in columns:
        await connection.exec_driver_sql(
            "ALTER TABLE spend_reservation ADD COLUMN created_at DATETIME"
        )
    if "outcome" not in columns:
        await connection.exec_driver_sql("ALTER TABLE spend_reservation ADD COLUMN outcome VARCHAR")


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
        self._lock = asyncio.Lock()

    async def reserve(self, principal_id: int, amount: float) -> str:
        micros = _micros(amount)
        if micros <= 0:
            raise ValueError("Reservation must be positive")
        day = self._clock().astimezone(UTC).date().isoformat()
        reservation_id = uuid4().hex
        async with self._lock, self._session() as session:
            # Serialize the read/check/write across workers and processes.
            await session.execute(text("BEGIN IMMEDIATE"))
            await session.execute(
                update(SpendReservationRow)
                .where(
                    SpendReservationRow.day == day,
                    SpendReservationRow.settled.is_(False),
                    SpendReservationRow.amount_micros > 0,
                    SpendReservationRow.created_at.is_not(None),
                    SpendReservationRow.created_at
                    <= self._clock().astimezone(UTC) - UNKNOWN_RESERVATION_TTL,
                )
                .values(amount_micros=0, outcome="released_unknown")
            )
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
                    created_at=self._clock().astimezone(UTC),
                    outcome="active",
                )
            )
            await session.commit()
        return reservation_id

    async def settle(self, reservation_id: str, actual_cost: float) -> None:
        micros = _micros(actual_cost)
        async with self._lock, self._session() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            record = await session.get(SpendReservationRow, reservation_id)
            if record is None:
                raise LookupError("Unknown spend reservation")
            if record.settled:
                return
            record.amount_micros = micros
            record.settled = True
            record.outcome = "settled"
            await session.commit()

    async def fail(self, reservation_id: str, outcome: str) -> None:
        if outcome not in {"timeout", "error", "cancelled", "missing_usage"}:
            raise ValueError("Invalid spend outcome")
        async with self._lock, self._session() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            record = await session.get(SpendReservationRow, reservation_id)
            if record is None:
                raise LookupError("Unknown spend reservation")
            if not record.settled:
                record.outcome = outcome
            await session.commit()

    async def summary(self) -> dict[str, float | int]:
        now = self._clock().astimezone(UTC)
        row = SpendReservationRow
        unsettled = row.settled.is_(False)
        active = and_(
            unsettled,
            row.outcome == "active",
            row.created_at.is_not(None),
            row.created_at > now - timedelta(minutes=5),
        )

        def total(condition, value):
            return func.coalesce(func.sum(case((condition, value), else_=0)), 0)

        async with self._session() as session:
            values = (
                await session.execute(
                    select(
                        total(row.settled.is_(True), row.amount_micros),
                        total(unsettled, row.amount_micros),
                        total(active, 1),
                        total(and_(unsettled, row.outcome == "timeout"), 1),
                        total(and_(unsettled, row.outcome.in_(["error", "cancelled"])), 1),
                        total(and_(unsettled, row.outcome == "missing_usage"), 1),
                        total(and_(unsettled, row.outcome == "released_unknown"), 1),
                        total(
                            and_(
                                unsettled,
                                row.outcome == "active",
                                or_(
                                    row.created_at.is_(None),
                                    row.created_at <= now - timedelta(minutes=5),
                                ),
                            ),
                            1,
                        ),
                        total(and_(unsettled, row.outcome.is_(None)), 1),
                    )
                )
            ).one()
        return {
            "settled_usd": int(values[0]) / 1_000_000,
            "unsettled_usd": int(values[1]) / 1_000_000,
            "active_count": int(values[2]),
            "timed_out_count": int(values[3]),
            "failed_count": int(values[4]),
            "missing_usage_count": int(values[5]),
            "released_unknown_count": int(values[6]),
            "stale_or_restart_count": int(values[7]),
            "legacy_unknown_count": int(values[8]),
        }
