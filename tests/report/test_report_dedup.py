from __future__ import annotations

from datetime import UTC, datetime

from astrafeed.domain import Item, Route, Verdict
from astrafeed.report.dedup import MergedItem, dedup_for_report


def _v(ch: str, eid: str, text: str, imp: int, interest: str) -> Verdict:
    return Verdict(
        item=Item(
            channel_ref=ch,
            external_id=eid,
            text=text,
            link=f"https://t.me/{ch}/{eid}",
            timestamp=datetime(2026, 6, 1, tzinfo=UTC),
        ),
        route=Route.REPORT,
        matched_interests=(interest,),
        summary=f"sum:{text}",
        importance=imp,
    )


def test_empty_returns_empty():
    assert dedup_for_report([]) == []


def test_same_text_two_channels_merges_with_max_importance():
    verdicts = [
        _v("aaa", "1", "Big news today", 3, "AI"),
        _v("bbb", "9", "Big news today", 5, "AI"),
    ]
    merged = dedup_for_report(verdicts)
    assert len(merged) == 1
    m = merged[0]
    assert isinstance(m, MergedItem)
    assert m.importance == 5  # max wins
    assert m.gist == "sum:Big news today"  # highest-importance member's summary
    assert [h for h, _link in m.sources] == ["aaa", "bbb"]  # first-seen order
    assert m.cluster_id  # populated


def test_distinct_items_not_merged():
    merged = dedup_for_report([_v("aaa", "1", "one", 2, "AI"), _v("bbb", "2", "two", 4, "Crypto")])
    assert len(merged) == 2


def test_empty_summary_gist_stays_empty_no_raw_text_leak():
    # Trust boundary: gist == verdict.summary only. An empty summary must NOT
    # fall back to raw item.text, or raw post text would cross the LLM boundary
    # into the strong editor (spec: "removes the v.summary or v.item.text leak").
    # The empty gist renders deterministically as "(без текста)" in code.
    v = _v("aaa", "1", "Big news today", 3, "AI")
    v = Verdict(
        item=v.item,
        route=v.route,
        matched_interests=v.matched_interests,
        summary="",
        importance=v.importance,
    )
    merged = dedup_for_report([v])
    assert len(merged) == 1
    assert merged[0].gist == ""
    assert "Big news today" not in merged[0].gist


def test_private_channel_source_uses_name_not_id():
    # Private channels have no public @handle: their link is t.me/c/<id>/<msg>,
    # which the handle regex would render as the opaque "c". Fall back to the
    # human-readable channel name so the report never shows a raw id/"c".
    v = Verdict(
        item=Item(
            channel_ref="id:1986831466",
            external_id="8",
            text="private post",
            link="https://t.me/c/1986831466/8",
            timestamp=datetime(2026, 6, 1, tzinfo=UTC),
            channel_name="Secret Channel",
        ),
        route=Route.REPORT,
        matched_interests=("AI",),
        summary="sum",
        importance=3,
    )
    merged = dedup_for_report([v])
    assert [h for h, _link in merged[0].sources] == ["Secret Channel"]


def test_public_channel_source_keeps_username_handle():
    merged = dedup_for_report([_v("durov", "1", "hi", 3, "AI")])
    assert [h for h, _link in merged[0].sources] == ["durov"]


def test_single_source_member_keys_and_neutral_defaults():
    # A single-source item must behave exactly as today: member_item_ids is just
    # its own (channel_ref, external_id) key, consumed set empty, anchor_link the
    # post link, first_ts its timestamp.
    merged = dedup_for_report([_v("aaa", "7", "solo", 4, "AI")])
    m = merged[0]
    assert m.member_item_ids == (("aaa", "7"),)
    assert m.consumed_member_item_ids == frozenset()
    assert m.anchor_link == "https://t.me/aaa/7"
    assert m.first_ts == datetime(2026, 6, 1, tzinfo=UTC)


def test_merged_member_keys_first_ts_and_anchor_from_representative():
    early = Verdict(
        item=Item(
            channel_ref="aaa",
            external_id="1",
            text="shared text",
            link="https://t.me/aaa/1",
            timestamp=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
        ),
        route=Route.REPORT,
        matched_interests=("AI",),
        summary="sum",
        importance=3,
    )
    late_top = Verdict(
        item=Item(
            channel_ref="bbb",
            external_id="9",
            text="shared text",
            link="https://t.me/bbb/9",
            timestamp=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        ),
        route=Route.REPORT,
        matched_interests=("AI",),
        summary="sum",
        importance=5,  # representative (max importance)
    )
    m = dedup_for_report([early, late_top])[0]
    # member keys preserve member (first-seen) order
    assert m.member_item_ids == (("aaa", "1"), ("bbb", "9"))
    # first_ts is the earliest member timestamp, not the representative's
    assert m.first_ts == datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    # anchor_link follows the representative (highest-importance) member
    assert m.anchor_link == "https://t.me/bbb/9"
    assert m.consumed_member_item_ids == frozenset()


def test_interest_union_dedup_first_seen_order():
    a = _v("aaa", "1", "shared text", 3, "AI")
    a = Verdict(
        item=a.item,
        route=a.route,
        matched_interests=("AI", "Crypto"),
        summary=a.summary,
        importance=a.importance,
    )
    b = _v("bbb", "9", "shared text", 5, "Crypto")
    b = Verdict(
        item=b.item,
        route=b.route,
        matched_interests=("Crypto", "Markets"),
        summary=b.summary,
        importance=b.importance,
    )
    merged = dedup_for_report([a, b])
    assert len(merged) == 1
    assert merged[0].interests == ("AI", "Crypto", "Markets")
