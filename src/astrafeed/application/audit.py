from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from astrafeed.config import AuditSettings
from astrafeed.domain.audit import AuditContext, AuditEvent, AuditEventKind
from astrafeed.ports.audit import AuditSink, AuditStore

_context: ContextVar[AuditContext | None] = ContextVar("audit_context", default=None)


@contextmanager
def audit_scope(context: AuditContext) -> Iterator[None]:
    token = _context.set(context)
    try:
        yield
    finally:
        _context.reset(token)


def current_audit_context() -> AuditContext | None:
    return _context.get()


@dataclass(frozen=True)
class AuditHealth:
    state: str
    dropped_events: int
    pending_events: int
    pending_bytes: int
    last_error_at: datetime | None
    last_persisted_at: datetime | None


@dataclass
class _QueuedEvent:
    event: AuditEvent
    size: int
    ack: asyncio.Event


class AuditRecorder(AuditSink):
    """A bounded best-effort sink: diagnostic persistence never delays business I/O."""

    def __init__(self, store: AuditStore, settings: AuditSettings) -> None:
        self._store = store
        self._settings = settings
        self._queue: asyncio.Queue[_QueuedEvent] = asyncio.Queue(maxsize=settings.queue_events)
        self._pending_bytes = 0
        self._dropped = 0
        self._state = "disabled" if not settings.enabled else "healthy"
        self._last_error_at: datetime | None = None
        self._last_persisted_at: datetime | None = None
        self._worker: asyncio.Task[None] | None = None
        self._closed = False

    def _event_bytes(self, event: AuditEvent) -> int:
        return len(
            json.dumps(event.data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )

    def _ensure_worker(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._write(), name="audit-recorder")

    def _enqueue(self, event: AuditEvent) -> _QueuedEvent | None:
        if self._closed or not self._settings.enabled:
            return None
        size = self._event_bytes(event)
        over_limit = size > self._settings.event_bytes or (
            self._pending_bytes + size > self._settings.queue_bytes
        )
        if over_limit:
            self._dropped += 1
            self._state = "degraded"
            return None
        item = _QueuedEvent(event, size, asyncio.Event())
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            self._dropped += 1
            self._state = "degraded"
            return None
        self._pending_bytes += size
        self._ensure_worker()
        return item

    def emit(self, event: AuditEvent) -> bool:
        if event.kind is AuditEventKind.EXECUTION_FINISHED:
            dropped = self._dropped
            stored = event.data.get("completeness") or "complete"
            completeness = "partial" if dropped else str(stored)
            event = replace(
                event,
                data={
                    **dict(event.data),
                    "dropped_events": dropped,
                    "completeness": completeness,
                },
            )
        return self._enqueue(event) is not None

    async def begin_attempt(self, event: AuditEvent) -> bool:
        item = self._enqueue(event)
        if item is None:
            return False
        try:
            await asyncio.wait_for(
                asyncio.shield(item.ack.wait()), self._settings.start_wait_seconds
            )
        except TimeoutError:
            return True
        return self._state != "degraded"

    async def _write(self) -> None:
        while not self._closed or not self._queue.empty():
            try:
                item = await self._queue.get()
            except asyncio.CancelledError:
                return
            try:
                await self._store.append((item.event,))
                self._last_persisted_at = datetime.now(UTC)
            except Exception:
                self._state = "degraded"
                self._last_error_at = datetime.now(UTC)
            finally:
                self._pending_bytes -= item.size
                self._queue.task_done()
                item.ack.set()

    async def flush(self, timeout: float) -> bool:
        if self._worker is None:
            return self._state != "degraded"
        try:
            await asyncio.wait_for(self._queue.join(), timeout)
        except TimeoutError:
            self._state = "degraded"
            return False
        return self._state != "degraded" and self._dropped == 0

    async def close(self, timeout: float) -> bool:
        self._closed = True
        ok = await self.flush(timeout)
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
        return ok

    def health(self) -> AuditHealth:
        return AuditHealth(
            state=self._state,
            dropped_events=self._dropped,
            pending_events=self._queue.qsize(),
            pending_bytes=self._pending_bytes,
            last_error_at=self._last_error_at,
            last_persisted_at=self._last_persisted_at,
        )


async def retention_loop(
    store: AuditStore,
    settings: AuditSettings,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Periodic payload/metadata TTL. Best-effort: a cleanup error degrades silently."""
    while True:
        await sleep(settings.cleanup_seconds)
        try:
            await store.cleanup(now=datetime.now(UTC), limit=settings.cleanup_limit)
        except Exception:
            continue
