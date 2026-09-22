"""Deterministic source adapter for offline runs and tests."""

from __future__ import annotations

from datetime import datetime

from astrafeed.domain import Channel, Item, Subscription


class FakeSource:
    def __init__(self, items: list[Item], *, truncated: bool = False) -> None:
        self._items = items
        self.truncated = truncated

    async def fetch_new_items(self, channel: Channel, since: datetime | None) -> list[Item]:
        items = [item for item in self._items if item.channel_ref == channel.telegram_ref]
        if since is not None:
            items = [item for item in items if item.timestamp > since]
        return sorted(items, key=lambda item: item.timestamp)

    async def list_subscribed_channels(self) -> list[Subscription]:
        return []
