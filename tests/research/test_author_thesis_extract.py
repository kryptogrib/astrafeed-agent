"""Isolation, span, id and matching rules for the author-thesis extraction experiment."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "docs" / "research"))

from author_thesis_extract import (  # noqa: E402
    EXTRACT_KEYS,
    accept_theses,
    extract_payload,
    leaks_extract,
    match_gold_to_extracted,
    stable_thesis_id,
    theses_for_linker,
)
from reaction_subject_v2 import check_item, context_for, id_contract, leaks  # noqa: E402

POST = (
    "Circle launched Arc yesterday. Analysts say it will flip Ethereum. "
    "I think ETH goes to 3k. Deposit via fomo: https://x.example/ref"
)
THREAD = {
    "thread": "https://t.me/chan/1",
    "topic": "eth",
    "post": {"text": POST, "published_at": "2026-09-11T09:00:00+00:00"},
    "events": [{"event_id": "e1", "quotes": ["Circle launched Arc yesterday."]}],
    "theses": [],
    "comments": [
        {
            "id": "eth|u/1",
            "url": "u/1",
            "published_at": "2026-09-11T10:00:00+00:00",
            "text": "3k is hopium",
            "chain": [],
        }
    ],
}


def test_extractor_input_is_only_the_post_and_requested_topic():
    payload = extract_payload(THREAD)
    assert set(payload) == EXTRACT_KEYS
    assert payload == {"requested_topic": "Ethereum / ETH", "post": POST}
    assert leaks_extract(THREAD, payload) == []
    leaked = {**payload, "comments": THREAD["comments"], "labels": [{"target": "author_thesis"}]}
    problems = leaks_extract(THREAD, leaked)
    assert any("comments" in p or "labels" in p or "fields" in p for p in problems)


def test_quote_must_equal_post_slice_wrong_or_ambiguous_spans_are_dropped():
    quote = "I think ETH goes to 3k."
    start = POST.index(quote)
    ok = accept_theses(
        THREAD,
        {
            "theses": [
                {
                    "thesis_id": "ignore-me",
                    "quote": quote,
                    "start": start,
                    "end": start + len(quote),
                    "kind": "forecast",
                    "topic_role": "subject",
                }
            ]
        },
    )
    assert len(ok["theses"]) == 1
    assert ok["theses"][0]["quote"] == POST[ok["theses"][0]["start"] : ok["theses"][0]["end"]]
    assert ok["theses"][0]["thesis_id"] == stable_thesis_id(THREAD["thread"], quote)

    for raw in (
        {"theses": [{"quote": quote, "start": start + 1, "end": start + len(quote), "kind": "forecast"}]},
        {"theses": [{"quote": "ETH goes to 4k", "start": start, "end": start + 14, "kind": "forecast"}]},
        {"theses": [{"quote": quote, "start": None, "end": None, "kind": "forecast"}]},
        {"theses": "not-a-list"},
        None,
    ):
        got = accept_theses(THREAD, raw)
        assert got["theses"] == []
        assert got["rejected"]


def test_more_than_three_theses_are_capped_and_overflow_is_explicit():
    quotes = [
        "I think ETH goes to 3k.",
        "Circle launched Arc yesterday.",
        "Analysts say it will flip Ethereum.",
        "Deposit via fomo: https://x.example/ref",
    ]
    raw = {
        "theses": [
            {
                "quote": q,
                "start": POST.index(q),
                "end": POST.index(q) + len(q),
                "kind": "evaluation",
                "topic_role": "context",
            }
            for q in quotes
        ],
        "truncated": True,
    }
    got = accept_theses(THREAD, raw)
    assert len(got["theses"]) == 3
    assert got["truncated"] is True
    assert got["overflow_dropped"] == 1


def test_gold_match_is_by_quote_overlap_not_by_model_declared_id():
    quote = "I think ETH goes to 3k."
    extracted = accept_theses(
        THREAD,
        {
            "theses": [
                {
                    "thesis_id": "model-invented-id",
                    "quote": quote,
                    "start": POST.index(quote),
                    "end": POST.index(quote) + len(quote),
                    "kind": "forecast",
                    "topic_role": "subject",
                }
            ]
        },
    )["theses"]
    gold = [
        {
            "gold_id": "gold:chan/1:eth-3k",
            "thread": THREAD["thread"],
            "quote": "ETH goes to 3k",
            "start": POST.index("ETH goes to 3k"),
            "end": POST.index("ETH goes to 3k") + len("ETH goes to 3k"),
            "origin": "author",
        }
    ]
    matched = match_gold_to_extracted(gold, extracted)
    assert matched["gold:chan/1:eth-3k"] == extracted[0]["thesis_id"]
    assert matched["gold:chan/1:eth-3k"] != "model-invented-id"
    assert match_gold_to_extracted(
        [{**gold[0], "quote": "no such claim", "start": 0, "end": 12}], extracted
    ) == {"gold:chan/1:eth-3k": None}


def test_linker_still_rejects_a_foreign_thesis_id_and_needs_a_concrete_id():
    theses = theses_for_linker(
        [
            {
                "thesis_id": "th-local",
                "quote": "I think ETH goes to 3k.",
            }
        ]
    )
    th = {**THREAD, "theses": theses}
    c = th["comments"][0]
    payload = context_for(th, c)
    assert payload["theses"] == theses
    assert leaks(th, c, payload) == []
    ok = {
        "target": "author_thesis",
        "target_id": "th-local",
        "comment_fragment": "3k is hopium",
        "context_fragment": "ETH goes to 3k",
    }
    assert check_item(ok, th, c)["status"] == "ok"
    assert check_item({**ok, "target_id": "foreign"}, th, c)["status"] == "invalid"
    assert id_contract(check_item({**ok, "target_id": None}, th, c))["status"] == "no_id"
