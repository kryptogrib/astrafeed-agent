from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from astrafeed.domain.audit import AuditEvent


class AuditSink(Protocol):
    def emit(self, event: AuditEvent) -> bool: ...

    async def begin_attempt(self, event: AuditEvent) -> bool: ...


class AuditStore(Protocol):
    async def append(self, events: Sequence[AuditEvent]) -> None: ...

    async def cleanup(self, *, now: datetime, limit: int) -> int: ...
