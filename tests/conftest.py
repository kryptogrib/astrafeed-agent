from datetime import UTC, datetime

from astrafeed.domain import Item


def make_item(external_id: str, text: str, *, channel_ref: str = "@c", hour: int = 12) -> Item:
    return Item(
        channel_ref=channel_ref,
        external_id=external_id,
        text=text,
        link=f"https://t.me/c/{external_id}",
        timestamp=datetime(2026, 6, 9, hour, tzinfo=UTC),
    )
