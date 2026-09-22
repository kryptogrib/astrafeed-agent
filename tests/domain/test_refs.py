from __future__ import annotations

import pytest

from astrafeed.domain.refs import (
    normalize_channel_ref,
    public_url_for_ref,
    repair_message_link,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@durov", "@durov"),
        ("durov", "@durov"),
        ("https://t.me/durov", "@durov"),
        ("http://t.me/durov", "@durov"),
        ("t.me/durov", "@durov"),
        ("https://t.me/durov/", "@durov"),
        ("  https://t.me/durov  ", "@durov"),
        ("https://telegram.me/durov", "@durov"),
    ],
)
def test_normalizes_public_refs(raw, expected):
    assert normalize_channel_ref(raw) == expected


@pytest.mark.parametrize(
    "invite",
    [
        "https://t.me/+AbC123def",
        "https://t.me/joinchat/AbC123",
    ],
)
def test_private_invites_pass_through(invite):
    # invite links cannot be reduced to an @username; keep them verbatim
    assert normalize_channel_ref(invite) == invite


def test_id_ref_passes_through():
    assert normalize_channel_ref("id:1986831466") == "id:1986831466"


def test_empty_raises():
    with pytest.raises(ValueError):
        normalize_channel_ref("   ")


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("@foo", "https://t.me/foo"),
        ("foo", "https://t.me/foo"),
        ("foo_bar123", "https://t.me/foo_bar123"),
        ("id:123", None),
        ("t.me/foo", None),  # URL-shaped: rejected by design
        ("https://t.me/foo", None),
        ("foo/bar", None),
        ("bad name", None),
        ("+invite", None),
        ("", None),
    ],
)
def test_public_url_for_ref(ref, expected):
    assert public_url_for_ref(ref) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://t.me/id:123/9", "https://t.me/c/123/9"),
        ("https://t.me/id:1719765440/399424", "https://t.me/c/1719765440/399424"),
        ("http://telegram.me/id:5/2", "http://telegram.me/c/5/2"),
        # Already-correct / unrelated links pass through untouched.
        ("https://t.me/c/123/9", "https://t.me/c/123/9"),
        ("https://t.me/foo/9", "https://t.me/foo/9"),
        ("https://example.com/id:1/2", "https://example.com/id:1/2"),
        ("", ""),
    ],
)
def test_repair_message_link(url, expected):
    assert repair_message_link(url) == expected
