"""Single Telegram-session collector over the shared IngestionStore.

``ensure_window`` returns per-source :class:`~astrafeed.domain.ingestion.Coverage`.
Errors of individual sources are never hidden:

* ``EnsureWindowResult.errors[source_id]`` is set when the source was
  unavailable, private, flood-delayed, skipped by a pilot limit, or otherwise
  failed. ``coverage[source_id].complete`` is then False. An empty window in
  that case is **not** complete coverage.
* Hitting a post cap stores what was read and leaves ``complete=False``
  with no error so a later retry can finish the interval.
* A finished interval with no items, no cap, and no error is ``complete=True``.

Telegram I/O runs with no SQL transaction open. FloodWait delays that source
until the wait expires and does not block other sources in the same call.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from astrafeed.config import Settings
from astrafeed.domain.ingestion import Coverage, Source, require_public_source_ref
from astrafeed.ports.ingestion import IngestionStore
from astrafeed.ports.source import PublicRefResolver, WindowRead, WindowReader

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionLimits:
    max_channels_first_run: int = 5
    max_posts_per_channel: int = 200
    max_posts_per_run: int = 1000


def limits_from_settings(cfg: Settings) -> IngestionLimits:
    return IngestionLimits(
        max_channels_first_run=cfg.ingestion_max_channels_first_run,
        max_posts_per_channel=cfg.ingestion_max_posts_per_channel,
        max_posts_per_run=cfg.ingestion_max_posts_per_run,
    )


class EnsureWindowResult(Mapping[int, Coverage]):
    """``source_id → Coverage`` plus a visible ``errors`` map. See module docstring."""

    def __init__(
        self,
        coverage: Mapping[int, Coverage],
        errors: Mapping[int, str] | None = None,
    ) -> None:
        self._coverage = dict(coverage)
        self.errors = dict(errors or {})

    def __getitem__(self, key: int) -> Coverage:
        return self._coverage[key]

    def __iter__(self):
        return iter(self._coverage)

    def __len__(self) -> int:
        return len(self._coverage)


class _RunBudget:
    def __init__(self, remaining: int) -> None:
        self._remaining = remaining
        self._lock = asyncio.Lock()

    async def reserve(self, want: int) -> int:
        async with self._lock:
            if self._remaining <= 0 or want <= 0:
                return 0
            got = min(want, self._remaining)
            self._remaining -= got
            return got

    async def refund(self, unused: int) -> None:
        if unused <= 0:
            return
        async with self._lock:
            self._remaining += unused


class IngestionCoordinator:
    """One in-flight Telegram read per source; overlapping callers share it."""

    def __init__(
        self,
        store: IngestionStore,
        reader: WindowReader,
        *,
        resolver: PublicRefResolver,
        limits: IngestionLimits | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._reader = reader
        self._resolver = resolver
        self._limits = limits or IngestionLimits()
        self._now = now or (lambda: datetime.now(UTC))
        self._source_locks: dict[int, asyncio.Lock] = {}
        self._delayed_until: dict[int, datetime] = {}

    def _lock_for(self, source_id: int) -> asyncio.Lock:
        lock = self._source_locks.get(source_id)
        if lock is None:
            lock = asyncio.Lock()
            self._source_locks[source_id] = lock
        return lock

    async def resolve_public_ref(self, ref: str) -> Source:
        public = require_public_source_ref(ref)
        telegram_id = await self._resolver.resolve_public_ref(public)
        return await self._store.upsert_source(telegram_id)

    async def ensure_window(
        self, source_ids: Sequence[int], start: datetime, end: datetime
    ) -> EnsureWindowResult:
        """Cover the window for EVERY source, reading at most N concurrently.

        ``max_channels_first_run`` bounds how many Telegram reads are in flight
        at once -- it is a concurrency limit, not a quota. It used to truncate
        the list and mark the remainder ``"first-run channel limit"``, which
        turned any user with more than N channels into a permanently failing
        first report: the Mini App caps subscriptions at
        ``max_monitored_channels`` (20) while this capped ingestion at 5, so
        channels 6..20 reported incomplete coverage forever and the job ended
        ``incomplete_coverage``. Batching instead keeps the same peak load on
        the Telegram session and still finishes the whole set.

        ``max_posts_per_run`` stays a single budget shared across all batches,
        so raising the channel count cannot multiply the per-run post ceiling.
        """
        ids = list(dict.fromkeys(source_ids))
        coverage: dict[int, Coverage] = {}
        errors: dict[int, str] = {}
        budget = _RunBudget(self._limits.max_posts_per_run)
        size = max(1, self._limits.max_channels_first_run)

        async def one(sid: int) -> tuple[int, Coverage, str | None]:
            try:
                async with self._lock_for(sid):
                    cov, err = await self._ensure_one(sid, start, end, budget)
                return sid, cov, err
            except Exception as e:  # noqa: BLE001 - per-source, must not abort the batch
                _log.warning("ingestion source %s failed: %s", sid, e)
                return sid, Coverage(start=start, end=end, complete=False), str(e)

        for offset in range(0, len(ids), size):
            batch = ids[offset : offset + size]
            pairs = await asyncio.gather(*[one(sid) for sid in batch])
            for sid, cov, err in pairs:
                coverage[sid] = cov
                if err:
                    errors[sid] = err
        if errors:
            # A bare count ("errors=4") cannot be acted on: the maintainer needs the
            # source and the reason to tell a private channel from a FloodWait.
            _log.warning(
                "ingestion incomplete: %s",
                "; ".join(f"source {sid}: {reason}" for sid, reason in sorted(errors.items())),
            )
        return EnsureWindowResult(coverage, errors)

    async def collect_active(
        self, source_ids: Sequence[int], start: datetime, end: datetime
    ) -> EnsureWindowResult:
        """Visit the entire shared union in bounded batches, not just one user's quota.

        ``ensure_window`` now batches internally, so this is a thin alias kept
        for call-site intent. Going through it no longer resets the per-run
        post budget once per batch, which previously let a long source list
        spend ``max_posts_per_run`` several times over in one call."""
        return await self.ensure_window(source_ids, start, end)

    async def _ensure_one(
        self,
        source_id: int,
        start: datetime,
        end: datetime,
        budget: _RunBudget,
    ) -> tuple[Coverage, str | None]:
        source = await self._store.get_source(source_id)
        if source is None:
            return Coverage(start=start, end=end, complete=False), f"source {source_id} not found"
        if source.telegram_id is None:
            return Coverage(start=start, end=end, complete=False), "not a Telegram source"

        existing = await self._store.coverage(source_id, start, end)
        if existing.complete:
            return existing, None

        until = self._delayed_until.get(source_id)
        now = self._now()
        if until is not None and now < until:
            delay_msg = f"delayed until {until.isoformat()}"
            return Coverage(start=start, end=end, complete=False), delay_msg
        if until is not None:
            self._delayed_until.pop(source_id, None)

        reserved = await budget.reserve(self._limits.max_posts_per_channel)
        if reserved <= 0:
            return Coverage(start=start, end=end, complete=False), "run post cap"

        # Resume only a proven prefix of this requested window. A timestamp alone
        # cannot skip unread IDs sharing its second; derive the ID cursor from raw cache.
        read_start = start
        after_id = None
        watermark = await self._store.get_ingest_watermark(source_id)
        if watermark is not None and start <= watermark <= end:
            boundary = max(start, watermark - timedelta(microseconds=1))
            prefix = await self._store.coverage(source_id, start, boundary)
            if prefix.complete or watermark == start:
                cached = await self._store.read_window(source_id, start, watermark)
                numeric_ids = [
                    int(item.external_id) for item in cached if item.external_id.isdigit()
                ]
                after_id = max(numeric_ids) if numeric_ids else None
                read_start = boundary

        try:
            if after_id is None:
                read = await self._reader.read_window(
                    source.telegram_id, read_start, end, max_posts=reserved
                )
            else:
                read = await self._reader.read_window(
                    source.telegram_id, read_start, end, max_posts=reserved, after_id=after_id
                )
        except Exception as e:  # noqa: BLE001 - surface per source, do not abort siblings
            await budget.refund(reserved)
            return Coverage(start=start, end=end, complete=False), str(e)

        await budget.refund(reserved - len(read.items))
        _coverage, error = await self._persist_read(source_id, read_start, end, read)
        return await self._store.coverage(source_id, start, end), error

    async def _persist_read(
        self,
        source_id: int,
        start: datetime,
        end: datetime,
        read: WindowRead,
    ) -> tuple[Coverage, str | None]:
        if read.delayed_until is not None:
            self._delayed_until[source_id] = read.delayed_until
            _log.warning(
                "ingestion flood wait: source_id=%s delayed_until=%s",
                source_id,
                read.delayed_until.isoformat(),
            )
            await self._store.mark_coverage(source_id, start, end, complete=False)
            return Coverage(start=start, end=end, complete=False), read.error or "FloodWait"

        if read.error:
            await self._store.mark_coverage(source_id, start, end, complete=False)
            return Coverage(start=start, end=end, complete=False), read.error

        if read.items:
            await self._store.store_items(source_id, read.items)
        elif end - start > timedelta(hours=1):
            # An errorless empty read is marked complete, so a source that
            # silently yields nothing looks healthy forever while contributing
            # zero items to every report. Only the log can show it.
            _log.warning(
                "ingestion read no items: source_id=%s window=%s..%s",
                source_id,
                start.isoformat(),
                end.isoformat(),
            )

        complete = not read.truncated
        await self._store.mark_coverage(source_id, start, end, complete=complete)
        progress = end if complete else None
        if read.truncated and read.items and all(item.external_id.isdigit() for item in read.items):
            progress = max(item.timestamp for item in read.items)
            prefix_end = progress - timedelta(microseconds=1)
            if prefix_end >= start:
                await self._store.mark_coverage(source_id, start, prefix_end, complete=True)
        if progress is not None:
            previous = await self._store.get_ingest_watermark(source_id)
            if previous is None or progress > previous:
                await self._store.set_ingest_watermark(source_id, progress)
        return Coverage(start=start, end=end, complete=complete), None
