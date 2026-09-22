"""Report composition result and scoring failure classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class TransientScoringError(Exception):
    """Provider transport or timeout while scoring. The stage is safe to retry."""


@dataclass(frozen=True)
class ReportAcknowledgement:
    """Queue records represented by a composed report."""

    queue_ids: tuple[int, ...] = ()
    composed_at: datetime | None = None


@dataclass(frozen=True)
class PreparedReport:
    """Rendered output plus the queue records it represents."""

    chunks: tuple[str, ...]
    acknowledgement: ReportAcknowledgement


_TRANSPORT_EXC_NAMES = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "TimeoutException",
    }
)


def is_transient_scoring_failure(exc: BaseException) -> bool:
    """True for transport/timeouts, including those wrapped by an SDK retry layer."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, TransientScoringError):
            return True
        if isinstance(current, TimeoutError | ConnectionError):
            return True
        if type(current).__name__ in _TRANSPORT_EXC_NAMES:
            return True
        current = current.__cause__ or current.__context__
    return False
