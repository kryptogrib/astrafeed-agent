from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from astrafeed.adapters.source.xpoz import XpozReader


class FakeTwitter:
    def __init__(self):
        self.calls = []

    async def get_posts_by_author(self, handle, **kwargs):
        self.calls.append(("posts", handle, kwargs))
        return SimpleNamespace(
            data=[SimpleNamespace(id="1")], pagination=SimpleNamespace(total_rows=1)
        )

    async def get_comments(self, post_id, **kwargs):
        self.calls.append(("comments", post_id, kwargs))
        return SimpleNamespace(
            data=[SimpleNamespace(id="2")], pagination=SimpleNamespace(total_rows=1)
        )

    async def search_posts(self, query, **kwargs):
        self.calls.append(("search", query, kwargs))
        return SimpleNamespace(
            data=[SimpleNamespace(id="3")], pagination=SimpleNamespace(total_rows=1)
        )


class FakeAccount:
    def __init__(self, remaining):
        self.remaining = remaining

    async def get_account_details(self):
        return SimpleNamespace(usage=SimpleNamespace(subscription_credits_remaining=self.remaining))


class FakeClient:
    def __init__(self, remaining):
        self.twitter = FakeTwitter()
        self.account = FakeAccount(remaining)

    async def connect(self):
        pass


@pytest.mark.asyncio
async def test_xpoz_reader_spends_only_within_reserved_free_balance():
    client = FakeClient(52)
    twitter = client.twitter
    reader = XpozReader(client)
    await reader.posts_by_author("WuBlockchain", datetime(2026, 9, 23, tzinfo=UTC))
    assert twitter.calls[0][0:2] == ("posts", "WuBlockchain")
    with pytest.raises(RuntimeError, match="credit reserve"):
        await reader.comments("123")
    assert len(twitter.calls) == 1


@pytest.mark.asyncio
async def test_xpoz_reader_uses_single_fast_call_per_post_and_thread():
    client = FakeClient(500)
    twitter = client.twitter
    reader = XpozReader(client)
    posts, incomplete = await reader.posts_by_author(
        "WuBlockchain", datetime(2026, 9, 23, tzinfo=UTC)
    )
    replies, reply_incomplete = await reader.comments("123")
    assert len(posts) == len(replies) == 1
    assert incomplete is False and reply_incomplete is False
    assert twitter.calls[0][2]["limit"] == 300
    assert twitter.calls[1][0:2] == ("comments", "123")


@pytest.mark.asyncio
async def test_xpoz_reader_searches_broad_crypto_in_one_call():
    client = FakeClient(500)
    twitter = client.twitter
    reader = XpozReader(client)
    posts, incomplete = await reader.search_crypto(datetime(2026, 9, 25, tzinfo=UTC))
    assert len(posts) == 1 and incomplete is False
    assert twitter.calls[0][0] == "search"
    assert "crypto" in twitter.calls[0][1]
    assert twitter.calls[0][2]["limit"] == 300


@pytest.mark.asyncio
async def test_xpoz_reader_refreshes_balance_before_each_paid_call():
    client = FakeClient(500)
    reader = XpozReader(client)
    await reader.search_crypto(datetime(2026, 9, 25, tzinfo=UTC))
    client.account.remaining = 51
    with pytest.raises(RuntimeError, match="credit reserve"):
        await reader.search_crypto(datetime(2026, 9, 25, tzinfo=UTC))
    assert len(client.twitter.calls) == 1
