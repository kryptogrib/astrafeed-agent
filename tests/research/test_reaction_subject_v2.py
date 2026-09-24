import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs" / "research"))

from reaction_subject_v2 import (  # noqa: E402
    apply_verdict,
    check_item,
    check_verdict,
    context_for,
    id_contract,
    leaks,
)

POST = "Aave now accepts gold as collateral. I think ETH goes to 3k."
EARLY = {
    "id": "aave|u/1",
    "url": "u/1",
    "published_at": "2026-09-11T09:47:35+00:00",
    "text": "gold in crypto, wow",
    "chain": [],
}
LATE = {
    "id": "aave|u/2",
    "url": "u/2",
    "published_at": "2026-09-11T10:22:45+00:00",
    "text": "да да, точно",
    "chain": [{"url": "u/1", "published_at": EARLY["published_at"], "text": EARLY["text"]}],
}
THREAD = {
    "topic": "aave",
    "post": {"text": POST, "published_at": "2026-09-11T09:00:00+00:00"},
    "events": [
        {
            "event_id": "e1",
            "headline": "Завтра листинг на другой бирже",
            "quotes": ["Aave now accepts gold as collateral."],
        },
        {"event_id": "e2", "headline": "Событие другого поста", "quotes": []},
    ],
    "theses": [{"thesis_id": "t1", "quote": "I think ETH goes to 3k."}],
    "comments": [EARLY, LATE],
}
EVENT = {
    "target": "event",
    "target_id": "e1",
    "comment_fragment": "gold in crypto",
    "context_fragment": "accepts gold",
}


def test_early_reply_does_not_see_a_later_sibling_and_later_one_sees_its_chain():
    early = context_for(THREAD, EARLY)
    assert LATE["text"] not in str(early)
    assert leaks(THREAD, EARLY, early) == []
    late = context_for(THREAD, LATE)
    assert late["reply_chain"] == [EARLY["text"]]
    assert leaks(THREAD, LATE, late) == []
    # the check runs on the payload actually sent: a later sibling slipped into the chain is caught
    assert leaks(THREAD, EARLY, {**early, "reply_chain": [LATE["text"]]})


def test_event_context_is_this_posts_quotes_not_a_group_headline_and_topic_is_explicit():
    p = context_for(THREAD, EARLY)
    assert p["events"] == [{"event_id": "e1", "quotes": ["Aave now accepts gold as collateral."]}]
    assert "Завтра" not in str(p)
    assert p["requested_topic"] == "Aave"


def test_malformed_foreign_id_or_unconfirmed_fragment_is_invalid_not_unclear():
    assert check_item(EVENT, THREAD, EARLY) == {
        "target": "event",
        "target_id": "e1",
        "status": "ok",
    }
    for bad in (
        None,
        {"target": "maybe"},
        {**EVENT, "target_id": "e2"},
        {**EVENT, "comment_fragment": "gold on chain"},
        {**EVENT, "context_fragment": "accepts silver"},
    ):
        got = check_item(bad, THREAD, EARLY)
        assert got["status"] == "invalid" and got["target"] is None
    assert check_item({"target": "unclear"}, THREAD, EARLY)["status"] == "ok"


def test_id_contract_applies_to_events_and_theses_before_verification():
    no_id = check_item({**EVENT, "target_id": None}, THREAD, EARLY)
    assert id_contract(no_id)["status"] == "no_id"
    thesis = {
        "target": "author_thesis",
        "target_id": None,
        "comment_fragment": "wow",
        "context_fragment": "ETH goes",
    }
    assert id_contract(check_item(thesis, THREAD, EARLY))["target"] == "unclear"


def test_only_an_explicit_valid_keep_confirms_an_event():
    pred = check_item(EVENT, THREAD, EARLY)
    keep = check_verdict({"verdict": "keep", "fragment": "gold in crypto"}, EARLY)
    assert apply_verdict(pred, keep)["target"] == "event"
    for v in (
        None,
        {},
        {"verdict": None},
        {"verdict": "keep", "fragment": "not in comment"},
        {"items": []},
    ):
        got = apply_verdict(pred, check_verdict(v, EARLY))
        assert got["status"] == "unverified" and got["target"] is None
    assert apply_verdict(pred, "reject")["target"] == "unclear"
    assert apply_verdict(pred, None)["status"] == "cache_miss"
