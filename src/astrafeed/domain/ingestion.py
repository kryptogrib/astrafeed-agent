"""Shared public-source catalog types.

A stored ``Source.telegram_id`` is catalog identity, not an access grant.
Resolving a public username (task 06) does not confer a right to read a
private channel. Invite/private refs are rejected here by shape only;
Telegram resolution is out of scope.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from astrafeed.domain.refs import normalize_channel_ref


@dataclass(frozen=True)
class Coverage:
    start: datetime
    end: datetime
    complete: bool


@dataclass(frozen=True)
class Source:
    id: int
    telegram_id: int


class PrivateSourceRefError(ValueError):
    """Invite/private refs cannot be catalogued as public sources."""


class SourceUnavailableError(LookupError):
    """Public ref could not be resolved, or the channel cannot be read."""


def require_public_source_ref(value: str) -> str:
    """Normalize a public ``@username``. Reject invite and private refs.

    This does not talk to Telegram; it only validates the reference shape.
    """
    raw = value.strip()
    if not raw:
        raise PrivateSourceRefError("empty source reference")
    lowered = raw.lower()
    private_markers = (
        "t.me/+",
        "telegram.me/+",
        "joinchat/",
        "t.me/c/",
        "telegram.me/c/",
    )
    if any(marker in lowered for marker in private_markers):
        raise PrivateSourceRefError("invite/private refs are not public sources")
    if lowered.startswith("id:") or "/id:" in lowered:
        raise PrivateSourceRefError("private channel refs are not public sources")
    ref = normalize_channel_ref(raw)
    if ref.startswith("id:") or not ref.startswith("@"):
        raise PrivateSourceRefError("invite/private refs are not public sources")
    if "://" in ref or "/" in ref.lstrip("@"):
        raise PrivateSourceRefError("invite/private refs are not public sources")
    return ref


def coverage_for_window(records: Sequence[Coverage], start: datetime, end: datetime) -> Coverage:
    """Whether ``[start, end]`` is fully covered by complete intervals."""
    spans = sorted((r.start, r.end) for r in records if r.complete)
    merged: list[list[datetime]] = []
    for span_start, span_end in spans:
        if not merged or span_start > merged[-1][1]:
            merged.append([span_start, span_end])
        else:
            merged[-1][1] = max(merged[-1][1], span_end)
    complete = any(span_start <= start and end <= span_end for span_start, span_end in merged)
    return Coverage(start=start, end=end, complete=complete)
