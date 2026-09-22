from __future__ import annotations

from datetime import UTC, datetime

from astrafeed.domain.models import Item
from astrafeed.domain.sources import extract_source_leads


def _item(text: str = "", forwarded_from_ref: str | None = None) -> Item:
    return Item(
        channel_ref="@home",
        external_id="1",
        text=text,
        link="https://t.me/home/1",
        timestamp=datetime(2026, 6, 12, tzinfo=UTC),
        forwarded_from_ref=forwarded_from_ref,
    )


def test_no_signals_yields_empty_set():
    assert extract_source_leads(_item(text="just words, no links"), source_ref="@home") == set()


def test_forward_ref_is_included_and_normalized():
    item = _item(forwarded_from_ref="foo")  # un-normalized on purpose
    assert extract_source_leads(item, source_ref="@home") == {"@foo"}


def test_tme_link_in_text_is_extracted():
    item = _item(text="see https://t.me/coolchan for more")
    assert extract_source_leads(item, source_ref="@home") == {"@coolchan"}


def test_bare_tme_link_without_scheme():
    item = _item(text="check t.me/barechan now")
    assert extract_source_leads(item, source_ref="@home") == {"@barechan"}


def test_deep_link_collapses_to_channel():
    item = _item(text="post here https://t.me/foo/123")
    assert extract_source_leads(item, source_ref="@home") == {"@foo"}


def test_query_string_is_stripped():
    item = _item(text="link https://t.me/foo?single")
    assert extract_source_leads(item, source_ref="@home") == {"@foo"}


def test_fragment_is_stripped():
    item = _item(text="link https://t.me/foo#section")
    assert extract_source_leads(item, source_ref="@home") == {"@foo"}


def test_deep_link_with_query_strips_both():
    item = _item(text="https://t.me/foo/123?comment=4")
    assert extract_source_leads(item, source_ref="@home") == {"@foo"}


def test_invite_plus_link_dropped():
    item = _item(text="join https://t.me/+AbC123def now")
    assert extract_source_leads(item, source_ref="@home") == set()


def test_invite_joinchat_link_dropped():
    item = _item(text="join https://t.me/joinchat/AbC123 now")
    assert extract_source_leads(item, source_ref="@home") == set()


def test_bare_at_mention_not_mined():
    item = _item(text="shoutout to @somebody, great stuff")
    assert extract_source_leads(item, source_ref="@home") == set()


def test_self_reference_excluded_from_forward():
    item = _item(forwarded_from_ref="@home")
    assert extract_source_leads(item, source_ref="@home") == set()


def test_self_reference_excluded_from_link():
    item = _item(text="our own https://t.me/home/9")
    assert extract_source_leads(item, source_ref="@home") == set()


def test_self_reference_match_is_normalization_aware():
    # source_ref given bare; a deep self-link must still be dropped
    item = _item(text="https://t.me/home/9")
    assert extract_source_leads(item, source_ref="home") == set()


def test_forward_and_links_are_unified():
    item = _item(
        text="also see t.me/alpha and https://t.me/beta/7",
        forwarded_from_ref="gamma",
    )
    assert extract_source_leads(item, source_ref="@home") == {"@alpha", "@beta", "@gamma"}


def test_telegram_me_host_supported():
    item = _item(text="https://telegram.me/legacychan")
    assert extract_source_leads(item, source_ref="@home") == {"@legacychan"}


def test_duplicate_links_collapse():
    item = _item(text="t.me/dup t.me/dup/2 https://t.me/dup?x")
    assert extract_source_leads(item, source_ref="@home") == {"@dup"}


def test_trailing_punctuation_is_trimmed():
    item = _item(text="see https://t.me/coolchan. Also (t.me/foo)!")
    assert extract_source_leads(item, source_ref="@home") == {"@coolchan", "@foo"}


def test_host_must_start_at_token_boundary():
    item = _item(text="list.me/foo and example.com/t.me/bar and not.me/baz")
    assert extract_source_leads(item, source_ref="@home") == set()


def test_usernames_are_casefolded():
    item = _item(text="t.me/Durov and t.me/durov")
    assert extract_source_leads(item, source_ref="@home") == {"@durov"}


def test_self_reference_is_case_insensitive_for_links():
    item = _item(text="https://t.me/Home/9")
    assert extract_source_leads(item, source_ref="@home") == set()


def test_self_reference_is_case_insensitive_for_forward():
    item = _item(forwarded_from_ref="Home")
    assert extract_source_leads(item, source_ref="@home") == set()
