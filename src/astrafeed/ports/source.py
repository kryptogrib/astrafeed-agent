from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from astrafeed.domain import Channel, Item, Subscription


class Source(Protocol):
    async def fetch_new_items(self, channel: Channel, since: datetime | None) -> list[Item]:
        """Return Items from `channel` newer than `since` (oldest-first)."""
        ...

    async def list_subscribed_channels(self) -> list[Subscription]:
        """Return the channels the underlying account is subscribed to."""
        ...


@dataclass(frozen=True)
class WindowRead:
    """Bounded ``[start, end]`` read. Truncation and errors are first-class.

    An empty ``items`` with ``error is None`` and ``truncated is False`` is a
    genuine empty window. ``error`` means the source was unavailable, private,
    or rate-limited — never treat that as complete coverage.
    """

    items: tuple[Item, ...]
    truncated: bool
    error: str | None = None
    delayed_until: datetime | None = None


class WindowReader(Protocol):
    """Optional capability for a closed-interval read with a post cap.

    Separate from :class:`Source` so ``FakeSource`` stays valid everywhere.
    """

    async def read_window(
        self,
        telegram_id: int,
        start: datetime,
        end: datetime,
        *,
        max_posts: int,
        channel_ref: str | None = None,
        after_id: int | None = None,
    ) -> WindowRead: ...


class PublicRefResolver(Protocol):
    async def resolve_public_ref(self, ref: str) -> int:
        """Return the canonical Telegram id for a public ``@username``."""
        ...


@dataclass(frozen=True)
class PublicChannel:
    telegram_id: int
    telegram_ref: str
    title: str


class PublicChannelResolver(Protocol):
    async def resolve_public_channel(self, ref: str) -> PublicChannel:
        """Verify public channel identity and read access, without joining it."""
        ...
