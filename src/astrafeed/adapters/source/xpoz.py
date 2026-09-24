"""Small Xpoz SDK adapter with a hard free-credit reserve."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from xpoz import ResponseType

POST_FIELDS = [
    "id",
    "text",
    "author_username",
    "created_at",
    "is_retweet",
    "reply_to_tweet_id",
    "reply_count",
]
COMMENT_FIELDS = ["id", "text", "author_username", "created_at", "reply_to_tweet_id"]
CALL_COST = 2
RESERVE_CREDITS = 50
CRYPTO_QUERY = "crypto OR bitcoin OR ethereum OR solana OR defi"


class XpozReader:
    def __init__(self, client: Any) -> None:
        self._client = client
        self._remaining: int | None = None

    async def refresh_balance(self) -> int:
        await self._client.connect()
        details = await self._client.account.get_account_details()
        remaining = getattr(getattr(details, "usage", None), "subscription_credits_remaining", None)
        if not isinstance(remaining, int):
            raise RuntimeError("Xpoz credit balance unavailable")
        self._remaining = (
            min(self._remaining, remaining) if self._remaining is not None else remaining
        )
        return self._remaining

    async def _reserve(self) -> None:
        # Account details are free; refresh before each paid request so other
        # consumers of the same key cannot silently spend our reserve.
        await self.refresh_balance()
        if self._remaining is None or self._remaining - CALL_COST < RESERVE_CREDITS:
            raise RuntimeError("Xpoz credit reserve reached")
        # Failed/unknown calls are conservatively counted as spent until the
        # next free account check.
        self._remaining -= CALL_COST

    async def posts_by_author(self, handle: str, start: datetime) -> tuple[list[object], bool]:
        await self._reserve()
        result = await self._client.twitter.get_posts_by_author(
            handle,
            start_date=start.date().isoformat(),
            fields=POST_FIELDS,
            response_type=ResponseType.FAST,
            limit=300,
            force_latest=True,
        )
        posts = list(result.data)
        truncated = len(posts) >= 300 or result.pagination.total_rows > len(posts)
        return posts, truncated

    async def search_crypto(self, start: datetime) -> tuple[list[object], bool]:
        await self._reserve()
        result = await self._client.twitter.search_posts(
            CRYPTO_QUERY,
            start_date=start.date().isoformat(),
            fields=POST_FIELDS,
            response_type=ResponseType.FAST,
            limit=300,
            filter_out_retweets=True,
            force_latest=True,
        )
        posts = list(result.data)
        truncated = len(posts) >= 300 or result.pagination.total_rows > len(posts)
        return posts, truncated

    async def comments(self, post_id: str) -> tuple[list[object], bool]:
        await self._reserve()
        result = await self._client.twitter.get_comments(
            post_id, fields=COMMENT_FIELDS, force_latest=True
        )
        comments = list(result.data)
        truncated = len(comments) >= 300 or result.pagination.total_rows > len(comments)
        return comments, truncated
