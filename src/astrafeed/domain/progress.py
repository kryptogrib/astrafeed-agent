"""Stable personal progress markers for equal-timestamp source pages."""


def processed_item_signature(channel_id: int, external_id: str) -> str:
    return f"processed-item:{channel_id}:{external_id}"
