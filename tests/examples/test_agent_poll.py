import json
from pathlib import Path

import httpx
import pytest
from examples.agent_poll import poll_once

ENDPOINT = "https://example.test/a2mcp/astrafeed"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_first_poll_saves_snapshot_without_claiming_changes(tmp_path: Path):
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == ENDPOINT
        assert json.loads(request.content) == {}
        return httpx.Response(
            200,
            json={"action": "agenda", "result": {"snapshot_id": "snap-A", "stories": []}},
        )

    cursor = tmp_path / "cursor"
    with _client(handle) as client:
        lines = poll_once(client, ENDPOINT, cursor)

    assert cursor.read_text() == "snap-A\n"
    assert lines == ["Saved baseline snap-A; run again to see report changes."]


def test_later_poll_prints_changed_cards_and_advances_cursor(tmp_path: Path):
    cursor = tmp_path / "cursor"
    cursor.write_text("snap-A\n")

    def handle(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"since_snapshot_id": "snap-A"}
        return httpx.Response(
            200,
            json={
                "action": "agenda",
                "result": {
                    "snapshot_id": "snap-B",
                    "response_mode": "delta",
                    "comparison_status": "ok",
                    "stories": [
                        {
                            "title": "HYPE listing",
                            "signals": {
                                "confirmation": "official",
                                "price": {"verdict": "both_moved"},
                            },
                        }
                    ],
                    "upcoming": [
                        {"title": "ETH ETF", "signals": {"confirmation": None, "price": None}}
                    ],
                },
            },
        )

    with _client(handle) as client:
        lines = poll_once(client, ENDPOINT, cursor)

    assert cursor.read_text() == "snap-B\n"
    assert lines == [
        "snap-A → snap-B: 2 new or updated report cards",
        "HYPE listing | confirmation=official | price.verdict=both_moved",
        "ETH ETF | confirmation=null | price.verdict=null",
    ]


def test_missing_baseline_rebuilds_from_full_report(tmp_path: Path):
    cursor = tmp_path / "cursor"
    cursor.write_text("snap-old\n")

    def handle(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"since_snapshot_id": "snap-old"}
        return httpx.Response(
            200,
            json={
                "action": "agenda",
                "result": {
                    "snapshot_id": "snap-C",
                    "response_mode": "full",
                    "comparison_status": "baseline_unavailable",
                    "stories": [{"title": "New story", "signals": None}],
                    "upcoming": [],
                },
            },
        )

    with _client(handle) as client:
        lines = poll_once(client, ENDPOINT, cursor)

    assert cursor.read_text() == "snap-C\n"
    assert lines == [
        "Baseline snap-old unavailable; rebuilt from full report snap-C (1 card).",
        "New story | confirmation=null | price.verdict=null",
    ]


def test_unchanged_report_does_not_invent_updates(tmp_path: Path):
    cursor = tmp_path / "cursor"
    cursor.write_text("snap-A\n")

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "action": "agenda",
                "result": {
                    "snapshot_id": "snap-A",
                    "response_mode": "delta",
                    "comparison_status": "ok",
                    "stories": [],
                    "upcoming": [],
                },
            },
        )

    with _client(handle) as client:
        lines = poll_once(client, ENDPOINT, cursor)

    assert lines == ["snap-A → snap-A: no new or updated report cards"]


def test_http_failure_keeps_previous_cursor(tmp_path: Path):
    cursor = tmp_path / "cursor"
    cursor.write_text("snap-A\n")

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with _client(handle) as client, pytest.raises(httpx.HTTPStatusError):
        poll_once(client, ENDPOINT, cursor)

    assert cursor.read_text() == "snap-A\n"


def test_explicit_baseline_allows_reproducible_comparison(tmp_path: Path):
    cursor = tmp_path / "cursor"

    def handle(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {"since_snapshot_id": "snap-pinned"}
        return httpx.Response(
            200,
            json={
                "action": "agenda",
                "result": {
                    "snapshot_id": "snap-current",
                    "response_mode": "delta",
                    "comparison_status": "ok",
                    "stories": [],
                    "upcoming": [],
                },
            },
        )

    with _client(handle) as client:
        lines = poll_once(client, ENDPOINT, cursor, since_snapshot_id="snap-pinned")

    assert lines == ["snap-pinned → snap-current: no new or updated report cards"]
    assert cursor.read_text() == "snap-current\n"


def test_explicit_target_pins_the_report_for_a_reproducible_demo(tmp_path: Path):
    cursor = tmp_path / "cursor"

    def handle(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == {
            "since_snapshot_id": "snap-before",
            "snapshot_id": "snap-after",
        }
        return httpx.Response(
            200,
            json={
                "action": "agenda",
                "result": {
                    "snapshot_id": "snap-after",
                    "response_mode": "delta",
                    "comparison_status": "ok",
                    "stories": [],
                    "upcoming": [],
                },
            },
        )

    with _client(handle) as client:
        lines = poll_once(
            client,
            ENDPOINT,
            cursor,
            since_snapshot_id="snap-before",
            snapshot_id="snap-after",
        )

    assert lines == ["snap-before → snap-after: no new or updated report cards"]
    assert cursor.read_text() == "snap-after\n"
