from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from reaction_subject import _chain, check_item, payload_for

THREAD = {
    "post": {"text": "Aave now accepts gold as collateral. I think ETH goes to 3k."},
    "events": [
        {
            "event_id": "e1",
            "headline": "Aave accepts gold",
            "quotes": ["Aave now accepts gold as collateral."],
        }
    ],
    "theses": [{"thesis_id": "t1", "quote": "I think ETH goes to 3k."}],
    "comments": [
        {"id": "c1", "text": "gold in crypto, wow", "chain": []},
        {"id": "c2", "text": "", "chain": []},
    ],
}


def test_claim_needs_exact_fragments_and_an_id_of_this_thread() -> None:
    c = THREAD["comments"][0]
    ok = {
        "target": "event",
        "target_id": "e1",
        "comment_fragment": "gold in crypto",
        "context_fragment": "accepts gold",
    }
    assert check_item(ok, THREAD, c) == {"target": "event", "target_id": "e1", "invalid": None}
    assert (
        check_item({**ok, "comment_fragment": "golden"}, THREAD, c)["invalid"] == "comment_fragment"
    )
    assert (
        check_item({**ok, "context_fragment": "Binance lists"}, THREAD, c)["invalid"]
        == "context_fragment"
    )
    assert check_item({**ok, "target_id": "e9"}, THREAD, c)["invalid"] == "target_id"
    assert check_item({**ok, "target": "author_thesis"}, THREAD, c)["invalid"] == "target_id"
    assert check_item({"target": "whatever"}, THREAD, c) == {
        "target": "unclear",
        "target_id": None,
        "invalid": None,
    }


def test_model_sees_only_earlier_replies_and_no_empty_comments() -> None:
    t = datetime(2026, 9, 11, tzinfo=UTC)
    root = SimpleNamespace(pub_id="a", parent_id=None, url="u/a", published_at=t, text="root")
    reply = SimpleNamespace(pub_id="b", parent_id="a", url="u/b", published_at=t, text="reply")
    later = SimpleNamespace(pub_id="c", parent_id="b", url="u/c", published_at=t, text="later")
    by_id = {x.pub_id: x for x in (root, reply, later)}
    assert [m["text"] for m in _chain(reply, by_id)] == ["root"]
    assert [m["text"] for m in _chain(later, by_id)] == ["root", "reply"]
    assert [c["id"] for c in payload_for(THREAD)["comments"]] == ["c1"]
