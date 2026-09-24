"""Unit tests for news-first Pulse: window/cutoff, footers, merge, counters, empty reaction."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from news_pulse_build import (
    NO_REACTION,
    _limitations,
    assemble_decisions,
    build_from_parts,
    render_markdown,
    write_run,
)
from news_pulse_classify import Observation, find_mentions, segment_publication
from news_pulse_events import EventObservation, group_counts, group_events
from news_pulse_link import link_comment
from news_pulse_load import (
    Publication,
    load_aliases,
    load_snapshot,
    parse_aliases_env,
    parse_window,
    previous_window,
    resolve_topic,
    window_dir_name,
)


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def _pub(
    pub_id: str,
    text: str,
    *,
    ts: str = "2026-09-18T12:00:00",
    source_id: int = 1,
    url: str = "",
    kind: str = "post",
    author_id: str | None = "a1",
    channel: str = "@ch",
) -> Publication:
    return Publication(
        pub_id=pub_id,
        platform="telegram",
        source_id=source_id,
        message_external_id=pub_id.split(":")[-1],
        author_id=author_id,
        published_at=_dt(ts),
        discovered_at=None,
        url=url or f"https://t.me/ch/{pub_id.split(':')[-1]}",
        text=text,
        parent_id=None,
        thread_id=pub_id,
        kind=kind,
        has_media=False,
        metadata={"channel": channel},
    )


def _obs(
    obs_id: str,
    *,
    kind: str = "event",
    actor: str | None = "sec",
    action: str | None = "approve",
    object: str | None = "tokenized stocks",
    qualifiers: dict | None = None,
    origin: str = "own",
    url: str = "",
    ts: str = "2026-09-18T12:00:00",
    pub_id: str = "tg:1:1",
    source_id: int = 1,
    quote: str | None = None,
    author_id: str | None = "a1",
) -> EventObservation:
    quote = quote if quote is not None else f"{obs_id}: {action} {object}"
    return EventObservation(
        obs_id=obs_id,
        publication_id=pub_id,
        source_id=source_id,
        author_id=author_id,
        published_at=_dt(ts),
        url=url or f"https://example.com/{obs_id}",
        kind=kind,
        actor=actor,
        action=action,
        object=object,
        qualifiers=qualifiers or {},
        origin=origin,
        quote=quote,
        span=(0, len(quote)),
        text_hash="",
    )


def test_date_only_window_is_utc_half_open_inclusive_by_days():
    w = parse_window("2026-09-17..2026-09-19")
    assert w.start == datetime(2026, 9, 17, tzinfo=UTC)
    assert w.end == datetime(2026, 9, 20, tzinfo=UTC)
    assert w.requested == "2026-09-17..2026-09-19"
    prev = previous_window(w)
    assert prev.requested == "2026-09-14..2026-09-16"
    assert prev.end == w.start
    assert prev.end - prev.start == w.end - w.start


def test_reuse_does_not_change_limitation_lines():
    class _Client:
        reuse = True

        class budget:
            stopped = False
            max_usd = 3.0

    window = parse_window("2026-09-17..2026-09-19")
    from news_pulse_load import Snapshot

    snap = Snapshot(
        window=window,
        cutoff=window.end,
        db_md5="x",
        sources={},
        publications=[],
        comments=[],
        dropped_after_cutoff=0,
    )
    rows = _limitations(snap, _Client(), 0)
    assert all("reuse" not in x.casefold() and "кэш" not in x.casefold() for x in rows)
    _Client.reuse = False
    assert _limitations(snap, _Client(), 0) == rows


def test_iso_datetime_window_is_exact_half_open_utc():
    w = parse_window("2026-09-16T06:10:19+00:00..2026-09-21T06:04:32+00:00")
    assert w.start == datetime(2026, 9, 16, 6, 10, 19, tzinfo=UTC)
    assert w.end == datetime(2026, 9, 21, 6, 4, 32, tzinfo=UTC)
    assert w.requested == "2026-09-16T06:10:19+00:00..2026-09-21T06:04:32+00:00"
    shifted = parse_window("2026-09-16T14:10:19+08:00..2026-09-21T14:04:32+08:00")
    assert shifted.start == w.start
    assert shifted.end == w.end
    prev = previous_window(w)
    assert prev.end == w.start
    assert prev.end - prev.start == w.end - w.start
    assert "T" in prev.requested


def test_window_output_dir_replaces_colon_and_plus():
    raw = "2026-09-16T06:10:19+00:00..2026-09-21T06:04:32+00:00"
    safe = window_dir_name(raw)
    assert ":" not in safe
    assert "+" not in safe
    assert window_dir_name("2026-09-09..2026-09-23") == "2026-09-09..2026-09-23"


def test_bad_window_raises():
    with pytest.raises(ValueError):
        parse_window("7d")
    with pytest.raises(ValueError):
        parse_window("2026-09-19..2026-09-17")
    with pytest.raises(ValueError):
        parse_window("2026-09-16T06:10:19..2026-09-21T06:04:32")


def _tiny_db(path: Path) -> Path:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE source (id INTEGER PRIMARY KEY, telegram_id INTEGER);
        CREATE TABLE raw_item (
            id INTEGER PRIMARY KEY, source_id INTEGER, external_id TEXT,
            timestamp TEXT, payload TEXT
        );
        CREATE TABLE comment (
            comment_key TEXT, source_id INTEGER, post_id TEXT, comment_id TEXT,
            parent_comment_id TEXT, ts TEXT, edited_at TEXT, text TEXT, link TEXT,
            author_key TEXT, has_media INTEGER, classified INTEGER
        );
        """
    )
    db.execute("INSERT INTO source VALUES (1, 100)")
    posts = [
        ("1", "2026-09-19 23:59:59.000000", "inside last day", "https://t.me/ch/1"),
        ("2", "2026-09-20 00:00:00.000000", "after window", "https://t.me/ch/2"),
        ("3", "2026-09-18 10:00:00.000000", "mid window", "https://t.me/ch/3"),
        ("4", "2026-09-16 23:59:59.000000", "before window", "https://t.me/ch/4"),
    ]
    for eid, ts, text, link in posts:
        payload = json.dumps(
            {
                "text": text,
                "timestamp": ts.replace(" ", "T") + "+00:00" if "T" not in ts else ts,
                "channel_ref": "@ch",
                "link": link,
                "external_id": eid,
            }
        )
        db.execute(
            "INSERT INTO raw_item (source_id, external_id, timestamp, payload) VALUES (1,?,?,?)",
            (eid, ts, payload),
        )
    db.execute(
        "INSERT INTO comment VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "1:10",
            1,
            "3",
            "10",
            None,
            "2026-09-18 11:00:00.000000",
            None,
            "ok",
            "https://t.me/ch/3?comment=10",
            "u1",
            0,
            0,
        ),
    )
    db.execute(
        "INSERT INTO comment VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "1:11",
            1,
            "3",
            "11",
            None,
            "2026-09-20 00:00:01.000000",
            None,
            "future comment",
            "https://t.me/ch/3?comment=11",
            "u2",
            0,
            0,
        ),
    )
    db.commit()
    db.close()
    return path


def _boundary_db(path: Path) -> Path:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE source (id INTEGER PRIMARY KEY, telegram_id INTEGER);
        CREATE TABLE raw_item (
            id INTEGER PRIMARY KEY, source_id INTEGER, external_id TEXT,
            timestamp TEXT, payload TEXT
        );
        CREATE TABLE comment (
            comment_key TEXT, source_id INTEGER, post_id TEXT, comment_id TEXT,
            parent_comment_id TEXT, ts TEXT, edited_at TEXT, text TEXT, link TEXT,
            author_key TEXT, has_media INTEGER, classified INTEGER
        );
        """
    )
    db.execute("INSERT INTO source VALUES (1, 100)")
    posts = [
        ("10", "2026-09-16T06:10:19+00:00", "at start"),
        ("11", "2026-09-21T06:04:32+00:00", "at end"),
        ("12", "2026-09-16T06:10:18+00:00", "before start"),
        ("13", "2026-09-18T12:00:00+00:00", "inside"),
    ]
    for eid, ts, text in posts:
        payload = json.dumps(
            {
                "text": text,
                "timestamp": ts,
                "channel_ref": "@ch",
                "link": f"https://t.me/ch/{eid}",
                "external_id": eid,
            }
        )
        db.execute(
            "INSERT INTO raw_item (source_id, external_id, timestamp, payload) VALUES (1,?,?,?)",
            (eid, ts.replace("T", " ").replace("+00:00", ".000000"), payload),
        )
    db.commit()
    db.close()
    return path


def test_iso_window_includes_start_excludes_end(tmp_path: Path):
    path = _boundary_db(tmp_path / "b.db")
    snap = load_snapshot(path, "2026-09-16T06:10:19+00:00..2026-09-21T06:04:32+00:00")
    texts = {p.text for p in snap.publications}
    assert texts == {"at start", "inside"}
    assert snap.cutoff == datetime(2026, 9, 21, 6, 4, 32, tzinfo=UTC)


def test_cutoff_drops_future_before_any_processing(tmp_path: Path):
    path = _tiny_db(tmp_path / "t.db")
    snap = load_snapshot(path, "2026-09-17..2026-09-19")
    texts = {p.text for p in snap.publications}
    assert "inside last day" in texts
    assert "mid window" in texts
    assert "after window" not in texts
    assert "before window" not in texts
    assert "future comment" not in {c.text for c in snap.comments}
    assert {c.text for c in snap.comments} == {"ok"}
    assert len(snap.comments) == 1
    assert snap.dropped_after_cutoff >= 1
    assert all(p.published_at < snap.cutoff for p in snap.publications)
    assert all(c.published_at < snap.cutoff for c in snap.comments)


def test_aliases_cover_zec_eth_and_extra():
    aliases = load_aliases("docs/research/entity_aliases.tsv", extra={"sol": ["solana", "солана"]})
    assert "zec" in aliases["zec"].confirmed or "zcash" in aliases["zec"].confirmed
    assert "зкеш" in aliases["zec"].confirmed
    assert "eth" in aliases["eth"].confirmed or "ethereum" in aliases["eth"].confirmed
    assert "solana" in aliases["sol"].confirmed


def test_aliases_cover_arc_and_aave_from_registry_or_env():
    extra = parse_aliases_env("arc:arc;aave:aave")
    aliases = load_aliases("docs/research/entity_aliases.tsv", extra=extra)
    arc = resolve_topic("arc", aliases)
    aave = resolve_topic("aave", aliases)
    assert "arc" in arc.confirmed
    assert "aave" in aave.confirmed
    assert find_mentions("Circle launched the Arc testnet today", arc)
    assert find_mentions("AAVE proposal passed on-chain", aave)


def test_quote_footer_mention_stays_local():
    topic = load_aliases("docs/research/entity_aliases.tsv")["eth"]
    pub = _pub(
        "tg:1:9",
        "Биток показывает силу в пятницу.\n\nBTC $80 200\nETH $2 552\nGRAM $1.37",
    )
    segs = segment_publication(pub, topic)
    bodies = [s for s in segs if s.role == "body"]
    quotes = [s for s in segs if s.role in {"quote_line", "footer"}]
    assert quotes, segs
    assert any(s.mentions for s in quotes)
    assert not any(s.is_candidate and s.role == "body" for s in bodies)
    assert not any(s.role == "body" and find_mentions(s.text, topic) for s in bodies)


def test_body_mention_is_candidate():
    topic = load_aliases("docs/research/entity_aliases.tsv")["zec"]
    pub = _pub("tg:1:8", "Сообщество Zcash проголосовало за блоки 25 сек.")
    segs = segment_publication(pub, topic)
    assert any(s.is_candidate and s.role == "body" for s in segs)


def test_no_merge_by_ticker_only():
    a = _obs(
        "a", actor="community", action="vote", object="zec", qualifiers={"change": "block-25s"}
    )
    b = _obs(
        "b",
        actor="trader",
        action="short",
        object="zec",
        qualifiers={"loss": "26m"},
        pub_id="tg:1:2",
    )
    groups = group_events([a, b])
    assert len(groups) == 2


def test_no_transitive_merge():
    a = _obs("a", actor="fund", action="approve", object="etf", qualifiers={"asset": "zec"})
    b = _obs(
        "b",
        actor="fund",
        action="approve",
        object="etf",
        qualifiers={"asset": "zec"},
        url="https://shared.example/x",
        pub_id="tg:1:2",
    )
    c = _obs(
        "c",
        actor="fund",
        action="review",
        object="etf",
        qualifiers={"asset": "eth"},
        url="https://shared.example/x",
        pub_id="tg:1:3",
    )
    groups = group_events([a, b, c])
    assert all(len(g.members) < 3 for g in groups)
    ids = [{m.obs_id for m in g.members} for g in groups]
    assert not any({"a", "b", "c"} <= s for s in ids)


def test_group_counters_separate_unknown_authors_and_reprints():
    members = [
        _obs("a", origin="own", author_id="alice", source_id=1, pub_id="tg:1:1"),
        _obs(
            "b",
            origin="retelling",
            author_id=None,
            source_id=2,
            pub_id="tg:2:1",
            url="https://example.com/a",
        ),
        _obs(
            "c",
            origin="unknown",
            author_id=None,
            source_id=2,
            pub_id="tg:2:2",
            url="https://example.com/a",
        ),
    ]
    counts = group_counts(members)
    assert counts["events"] == 1
    assert counts["publications"] == 3
    assert counts["channels"] == 2
    assert counts["known_authors"] == 1
    assert counts["unknown_authors"] == 2
    assert counts["found_origins"] == 1
    assert counts["reprints"] == 1
    assert counts["unknown_origin"] == 1


def test_group_counters_count_unique_publications_not_observations():
    """Два сегмента одной публикации не удваивают origin/авторов."""
    members = [
        _obs(
            "a1",
            origin="own",
            author_id=None,
            source_id=1,
            pub_id="tg:1:9",
            url="https://t.me/ch/9",
        ),
        _obs(
            "a2",
            origin="own",
            author_id=None,
            source_id=1,
            pub_id="tg:1:9",
            url="https://t.me/ch/9",
        ),
        _obs(
            "b",
            origin="retelling",
            author_id="bob",
            source_id=2,
            pub_id="tg:2:1",
            url="https://t.me/other/1",
        ),
    ]
    counts = group_counts(members)
    assert counts["publications"] == 2
    assert counts["channels"] == 2
    assert counts["known_authors"] == 1
    assert counts["unknown_authors"] == 1
    assert counts["found_origins"] == 1
    assert counts["reprints"] == 1
    assert counts["unknown_origin"] == 0


def test_news_without_comments_says_reaction_not_found():
    event = {
        "event_id": "e1",
        "headline": "Zcash ускоряет блоки",
        "counts": {"events": 1, "publications": 1, "channels": 1},
        "members": [
            {"publication_id": "tg:1:1", "url": "https://t.me/ch/1", "quote": "блоки 25 сек"}
        ],
    }
    payload = build_from_parts(
        topic="zec",
        window="2026-09-17..2026-09-19",
        events=[event],
        positions=[],
        discussion=[],
        changes={
            "events_appeared": ["e1"],
            "source_coverage": {"added_channels": [], "removed_channels": []},
        },
        coverage={"publications": 1, "comments": 0, "channels": 1},
        limitations=["нет времени обнаружения"],
        evidence=[{"id": "ev1", "url": "https://t.me/ch/1", "quote": "блоки 25 сек"}],
    )
    assert NO_REACTION in payload["discussion"][0]["text"]
    md = render_markdown(payload)
    assert NO_REACTION in md
    assert "аудитория не отреагировала" not in md.lower()


def test_discussion_only_when_no_news():
    payload = build_from_parts(
        topic="zec",
        window="2026-09-17..2026-09-19",
        events=[],
        positions=[],
        discussion=[
            {
                "target": "topic_level",
                "text": "Спрашивают, покажет ли DASH себя как младший брат ZEC",
                "basis": "комментарий называет ZEC, новости в окне нет",
                "url": "https://t.me/ch/1?comment=2",
                "quote": "DASH тоже себя ещё покажет как младший брат от ZEC",
            }
        ],
        changes={
            "events_appeared": [],
            "source_coverage": {"added_channels": [], "removed_channels": []},
        },
        coverage={"publications": 0, "comments": 1, "channels": 1},
        limitations=[],
        evidence=[],
    )
    assert payload["events"] == []
    assert payload["discussion"]
    md = render_markdown(payload)
    assert "новост" in md.lower()
    assert "DASH" in md or "младший брат" in md


def test_comment_is_not_grouped_as_news_event():
    from news_pulse_classify import Observation
    from news_pulse_events import from_observation

    comment_obs = Observation(
        obs_id="c1",
        publication_id="telegram:1:1:c:9",
        source_id=1,
        author_id="u1",
        published_at=_dt("2026-09-18T12:00:00"),
        url="https://t.me/ch/1?comment=9",
        span=(0, 10),
        quote="держу zec",
        kind="participant_reaction",
        actor=None,
        action=None,
        object="zec",
        qualifiers={},
        origin="own",
        source_role="participant",
        verification_status="unverified",
        topic_mentions=[{"text": "zec", "status": "confirmed"}],
        status="ok",
        text="держу zec",
    )
    groups = group_events([from_observation(comment_obs)])
    assert groups == []


def test_link_doubt_stays_topic_level():
    comment = _pub("tg:1:c1", "Жалоба: NFT-сайт в экосистеме ZEC не открывается", kind="comment")
    events = [
        {
            "event_id": "e-net",
            "headline": "Сбой сети ZEC",
            "object": "zcash network",
            "members": [{"publication_id": "tg:1:1", "quote": "сеть недоступна"}],
        }
    ]
    link = link_comment(comment, events, theses=[], post_observations=[])
    assert link["target"] == "other_subject"
    assert link["basis"]


def test_decisions_json_matches_contract(tmp_path: Path):
    topic = load_aliases("docs/research/entity_aliases.tsv")["zec"]
    event_pub = _pub(
        "telegram:1:1", "Сообщество Zcash проголосовало за блоки 25 сек.", ts="2026-09-18T12:00:00"
    )
    footer_pub = _pub(
        "telegram:1:2",
        "Рынок в плюсе.\n\nBTC $80 200\nZEC $42",
        ts="2026-09-18T13:00:00",
        source_id=2,
        url="https://t.me/ch/2",
    )
    comment = _pub(
        "telegram:1:1:c:9",
        "держу zec",
        ts="2026-09-18T14:00:00",
        kind="comment",
        url="https://t.me/ch/1?comment=9",
    )
    comment.metadata["comment_key"] = "channel:1:9"
    event = {
        "event_id": "e1-abc",
        "headline": "Zcash ускоряет блоки",
        "counts": {
            "publications": 1,
            "channels": 1,
            "known_authors": 1,
            "found_origins": 1,
            "reprints": 0,
            "unknown_origin": 0,
        },
        "members": [
            {
                "publication_id": event_pub.pub_id,
                "url": event_pub.url,
                "quote": "проголосовало за блоки 25 сек",
                "origin": "own",
                "source_id": 1,
                "author_id": "a1",
            }
        ],
    }
    obs = [
        Observation(
            obs_id="s1",
            publication_id=event_pub.pub_id,
            source_id=1,
            author_id="a1",
            published_at=event_pub.published_at,
            url=event_pub.url,
            span=(0, len(event_pub.text)),
            quote=event_pub.text,
            kind="event",
            actor="community",
            action="vote",
            object="zec",
            qualifiers={},
            origin="own",
            source_role="author",
            verification_status="unverified",
            topic_mentions=[{"text": "Zcash", "status": "confirmed"}],
            status="ok",
            text=event_pub.text,
        ),
        Observation(
            obs_id="s2",
            publication_id=footer_pub.pub_id,
            source_id=2,
            author_id="a1",
            published_at=footer_pub.published_at,
            url=footer_pub.url,
            span=(20, len(footer_pub.text)),
            quote="ZEC $42",
            kind="promo_service",
            actor=None,
            action=None,
            object=None,
            qualifiers={},
            origin="unknown",
            source_role="unknown",
            verification_status="unverified",
            topic_mentions=[{"text": "ZEC", "status": "confirmed"}],
            status="ok",
            segment_role="footer",
            text="ZEC $42",
        ),
    ]
    window = parse_window("2026-09-17..2026-09-19")
    decisions = assemble_decisions(
        topic=topic.topic,
        window=window,
        publications=[event_pub, footer_pub],
        comments=[comment],
        topic_spec=topic,
        observations=obs,
        events=[event],
        comment_links={
            comment.pub_id: {
                "target": "event",
                "target_id": "e1-abc",
                "basis": "реплика к посту с одним событием",
                "url": comment.url,
            }
        },
    )
    assert decisions["topic"] == "zec"
    assert decisions["window"] == {
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "interval": "[start,end)",
    }
    pubs = {row["external_id"]: row for row in decisions["publications"]}
    assert set(pubs) == {"1", "2"}
    assert pubs["1"]["selected_news"] is True
    assert pubs["1"]["topic_mention"] is True
    assert pubs["1"]["event_ids"] == ["e1-abc"]
    assert pubs["1"]["origin"] == "own"
    assert pubs["1"]["source_role"] == "author"
    assert pubs["1"]["status"] == "processed"
    assert pubs["1"]["link"] == "https://t.me/ch/1"
    assert pubs["2"]["selected_news"] is False
    assert pubs["2"]["topic_mention"] is True
    assert pubs["2"]["event_ids"] == []
    assert pubs["1"]["segments"][0]["class"] == "event"
    assert pubs["1"]["segments"][0]["quote"] == event_pub.text
    assert "start" in pubs["1"]["segments"][0] and "end" in pubs["1"]["segments"][0]
    c0 = decisions["comments"][0]
    assert c0["comment_key"] == "channel:1:9"
    assert c0["link"] == "https://t.me/ch/1?comment=9"
    assert c0["link_target"] == "event:e1-abc"
    assert c0["basis"]
    ev = decisions["events"][0]
    assert ev["event_id"] == "e1-abc"
    assert ev["publications"] == [event_pub.url]
    assert ev["n_publications"] == 1
    assert ev["n_channels"] == 1
    assert ev["n_known_authors"] == 1
    assert ev["found_origins"] == [event_pub.url]
    assert ev["n_reprints"] == 0
    assert ev["n_unknown_origin"] == 0

    out = write_run(
        build_from_parts(
            topic="zec",
            window=window.requested,
            events=[event],
            positions=[],
            discussion=[],
            changes={
                "events_appeared": [],
                "source_coverage": {"added_channels": [], "removed_channels": []},
            },
            coverage={},
            limitations=[],
            evidence=[],
        ),
        "zec",
        window.requested,
        "md5",
        decisions=decisions,
        root=tmp_path,
    )
    saved = json.loads((out / "decisions.json").read_text())
    assert saved == decisions
    assert ":" not in out.name or window.requested == out.name


def _counts_from_decisions(decisions: dict, event_id: str) -> dict:
    """Независимый пересчёт: уникальные публикации группы и origin из decisions.publications."""
    pubs = [p for p in decisions["publications"] if event_id in (p.get("event_ids") or [])]
    uniq: dict[str, dict] = {}
    for p in pubs:
        uniq[p["link"]] = p
    rows = list(uniq.values())
    return {
        "events": 1,
        "publications": len(rows),
        "channels": len({p["source_id"] for p in rows}),
        "known_authors": len({p.get("author_id") for p in rows if p.get("author_id")}),
        "unknown_authors": sum(1 for p in rows if not p.get("author_id")),
        "found_origins": sum(1 for p in rows if p.get("origin") == "own"),
        "reprints": sum(1 for p in rows if p.get("origin") in {"retelling", "repost"}),
        "unknown_origin": sum(1 for p in rows if p.get("origin") == "unknown"),
        "origin_links": sorted(p["link"] for p in rows if p.get("origin") == "own"),
    }


def test_pulse_counters_recomputed_from_decisions_json(tmp_path: Path):
    """pulse.json и decisions.json согласованы: счётчики группы — уникальные публикации."""
    topic = load_aliases("docs/research/entity_aliases.tsv")["zec"]
    pub_a = _pub("telegram:1:9", "Сообщество Zcash проголосовало за блоки 25 сек.", author_id=None)
    pub_b = _pub(
        "telegram:2:1",
        "Пересказ: сообщество ZCash поддержало ускорение блоков до 25 сек.",
        source_id=2,
        url="https://t.me/other/1",
        author_id="bob",
    )
    event = {
        "event_id": "e-25s",
        "headline": "Zcash ускоряет блоки",
        "counts": {
            "events": 1,
            "publications": 3,
            "channels": 3,
            "known_authors": 3,
            "unknown_authors": 3,
            "found_origins": 3,
            "reprints": 3,
            "unknown_origin": 3,
        },
        "members": [
            {
                "obs_id": "s1",
                "publication_id": pub_a.pub_id,
                "url": pub_a.url,
                "quote": "проголосовало за блоки 25 сек",
                "origin": "own",
                "source_id": 1,
                "author_id": None,
            },
            {
                "obs_id": "s1b",
                "publication_id": pub_a.pub_id,
                "url": pub_a.url,
                "quote": "дополнительный сегмент той же публикации",
                "origin": "own",
                "source_id": 1,
                "author_id": None,
            },
            {
                "obs_id": "s2",
                "publication_id": pub_b.pub_id,
                "url": pub_b.url,
                "quote": "поддержало ускорение блоков до 25 сек",
                "origin": "retelling",
                "source_id": 2,
                "author_id": "bob",
            },
        ],
    }
    obs = [
        Observation(
            obs_id="s1",
            publication_id=pub_a.pub_id,
            source_id=1,
            author_id=None,
            published_at=pub_a.published_at,
            url=pub_a.url,
            span=(0, 20),
            quote="проголосовало за блоки 25 сек",
            kind="event",
            actor="community",
            action="vote",
            object="block time",
            qualifiers={"duration": "25s"},
            origin="own",
            source_role="editorial",
            verification_status="unverified",
            topic_mentions=[{"text": "Zcash", "status": "confirmed"}],
            status="ok",
            text=pub_a.text,
        ),
        Observation(
            obs_id="s1b",
            publication_id=pub_a.pub_id,
            source_id=1,
            author_id=None,
            published_at=pub_a.published_at,
            url=pub_a.url,
            span=(20, 40),
            quote="дополнительный сегмент",
            kind="event",
            actor="community",
            action="vote",
            object="block time",
            qualifiers={"duration": "25s"},
            origin="own",
            source_role="editorial",
            verification_status="unverified",
            topic_mentions=[{"text": "Zcash", "status": "confirmed"}],
            status="ok",
            text=pub_a.text,
        ),
        Observation(
            obs_id="s2",
            publication_id=pub_b.pub_id,
            source_id=2,
            author_id="bob",
            published_at=pub_b.published_at,
            url=pub_b.url,
            span=(0, 30),
            quote="поддержало ускорение блоков до 25 сек",
            kind="event",
            actor="community",
            action="support",
            object="blocks",
            qualifiers={"duration": "25s"},
            origin="retelling",
            source_role="editorial",
            verification_status="unverified",
            topic_mentions=[{"text": "ZCash", "status": "confirmed"}],
            status="ok",
            text=pub_b.text,
        ),
    ]
    window = parse_window("2026-09-17..2026-09-19")
    decisions = assemble_decisions(
        topic=topic.topic,
        window=window,
        publications=[pub_a, pub_b],
        comments=[],
        topic_spec=topic,
        observations=obs,
        events=[event],
        comment_links={},
    )
    expected = _counts_from_decisions(decisions, "e-25s")
    ev = next(e for e in decisions["events"] if e["event_id"] == "e-25s")
    assert ev["n_publications"] == expected["publications"] == 2
    assert ev["n_channels"] == expected["channels"] == 2
    assert ev["n_known_authors"] == expected["known_authors"] == 1
    assert ev["n_reprints"] == expected["reprints"] == 1
    assert ev["n_unknown_origin"] == expected["unknown_origin"] == 0
    assert ev["found_origins"] == expected["origin_links"] == [pub_a.url]
    assert expected["found_origins"] == 1
    assert expected["unknown_authors"] == 1

    event["counts"] = {
        k: expected[k]
        for k in (
            "events",
            "publications",
            "channels",
            "known_authors",
            "unknown_authors",
            "found_origins",
            "reprints",
            "unknown_origin",
        )
    }
    payload = build_from_parts(
        topic="zec",
        window=window.requested,
        events=[event],
        positions=[],
        discussion=[],
        changes={
            "events_appeared": [],
            "source_coverage": {"added_channels": [], "removed_channels": []},
        },
        coverage={
            "topic_publications": sum(
                1 for p in decisions["publications"] if p.get("selected_news")
            )
        },
        limitations=[],
        evidence=[],
    )
    out = write_run(payload, "zec", window.requested, "md5", decisions=decisions, root=tmp_path)
    pulse = json.loads((out / "pulse.json").read_text())
    saved = json.loads((out / "decisions.json").read_text())
    recomputed = _counts_from_decisions(saved, "e-25s")
    pc = pulse["events"][0]["counts"]
    for key in (
        "publications",
        "channels",
        "known_authors",
        "unknown_authors",
        "found_origins",
        "reprints",
        "unknown_origin",
    ):
        assert pc[key] == recomputed[key], key
    assert pulse["coverage"]["topic_publications"] == sum(
        1 for p in saved["publications"] if p["selected_news"]
    )
    pubs = {p["link"]: p for p in saved["publications"]}
    assert pubs[pub_a.url].get("author_id") is None
    assert pubs[pub_b.url].get("author_id") == "bob"


def test_retellings_of_25s_vote_merge_across_formulations():
    a = _obs(
        "ru-vote",
        actor="сообщество zcash",
        action="проголосовало",
        object="ускорение блоков",
        qualifiers={"duration": "25 сек"},
        quote="Сообщество ZCash проголосовало за ускорение формирования блоков до 25 сек!",
        pub_id="tg:1:1",
    )
    b = _obs(
        "en-support",
        actor="zcash community",
        action="supported",
        object="block time reduction",
        qualifiers={"block_time": "25 seconds"},
        quote="The Zcash community supported reducing block time from 75 to 25 seconds.",
        pub_id="tg:2:1",
        source_id=2,
        url="https://t.me/other/1",
    )
    groups = group_events([a, b])
    assert len(groups) == 1
    assert {m.obs_id for m in groups[0].members} == {"ru-vote", "en-support"}


def test_vote_result_does_not_merge_with_later_upgrade_plan():
    vote = _obs(
        "vote",
        actor="zcash",
        action="vote",
        object="nu7",
        qualifiers={"stage": "vote"},
        quote="Zcash завершит голосование по составу обновления сети NU7",
        pub_id="tg:1:1",
    )
    plan = _obs(
        "plan",
        actor="zcash",
        action="upgrade",
        object="nu7",
        qualifiers={"event_date": "5 ноября", "stage": "activation"},
        quote="Zcash запланировал на 5 ноября обновление NU7",
        pub_id="tg:1:2",
        url="https://t.me/ch/2",
    )
    groups = group_events([vote, plan])
    assert len(groups) == 2


def test_etf_redistribution_enters_event_groups():
    from news_pulse_build import observations_for_events

    o = Observation(
        obs_id="s-etf",
        publication_id="telegram:1:11",
        source_id=1,
        author_id=None,
        published_at=_dt("2026-09-18T12:00:00"),
        url="https://t.me/ch/11",
        span=(0, 20),
        quote="ETH ETF: отток $224M",
        kind="redistribution",
        actor=None,
        action="outflow",
        object="etf",
        qualifiers={"amount": "224"},
        origin="retelling",
        source_role="editorial",
        verification_status="unverified",
        topic_mentions=[{"text": "ETH", "status": "confirmed"}],
        status="ok",
        text="ETH ETF: отток $224M",
    )
    rows = observations_for_events([o])
    assert len(rows) == 1
    assert rows[0].kind == "event"
    groups = group_events(rows)
    assert len(groups) == 1


def test_etf_flow_line_is_event_candidate_not_quote_footer():
    topic = load_aliases("docs/research/entity_aliases.tsv")["eth"]
    pub = _pub(
        "telegram:1:11",
        "₿ BTC: $76,532\n⟠ ETH: $2,437\n\n📈 🔴 ETH ETF: отток $224M",
    )
    segs = segment_publication(pub, topic)
    flow = [s for s in segs if "ETF" in s.text and "отток" in s.text]
    assert flow
    assert all(s.role == "body" and s.is_candidate for s in flow)
    prices = [s for s in segs if s.role in {"quote_line", "footer"}]
    assert prices


def test_digest_quote_line_does_not_make_post_news():
    topic = load_aliases("docs/research/entity_aliases.tsv")["eth"]
    pub = _pub(
        "telegram:1:9",
        "Биток показывает силу в пятницу.\n\nBTC $80 200\nETH $2 552\nGRAM $1.37",
    )
    from news_pulse_classify import classify_segments

    obs = classify_segments([pub], topic, llm=None)
    window = parse_window("2026-09-17..2026-09-19")
    decisions = assemble_decisions(
        topic=topic.topic,
        window=window,
        publications=[pub],
        comments=[],
        topic_spec=topic,
        observations=obs,
        events=[],
        comment_links={},
    )
    row = decisions["publications"][0]
    assert row["topic_mention"] is True
    assert row["selected_news"] is False
    assert row["event_ids"] == []


def test_digest_event_line_is_local_observation_not_whole_post_class():
    topic = load_aliases("docs/research/entity_aliases.tsv")["eth"]
    pub = _pub(
        "telegram:1:10",
        "📆 Основные события недели\n\n🔓 Разлоки: Akedo\n"
        "🇷🇺 Мосбиржа запускает бессрочные фьючерсы на индексы #BTC, #ETH, #SOL\n"
        "👋 Bitmex прекратит работу",
    )
    segs = segment_publication(pub, topic)
    eth_segs = [s for s in segs if s.mentions]
    assert eth_segs
    assert all(find_mentions(s.text, topic) for s in eth_segs)
    assert not any(find_mentions(s.text, topic) for s in segs if "Bitmex" in s.text)


def test_price_alert_only_post_is_news_candidate():
    topic = load_aliases("docs/research/entity_aliases.tsv")["zec"]
    pub = _pub("telegram:14:8099", "#zec = 1400$ say GM 🏆")
    segs = segment_publication(pub, topic)
    assert any(s.is_candidate and s.mentions for s in segs)


def test_comment_links_to_single_parent_event_on_subject():
    comment = _pub(
        "tg:14:c:188801",
        "Я этого гандона хотел лонговать когда он был по 450",
        kind="comment",
        url="https://t.me/icryptocom/8099?comment=188801",
    )
    comment.metadata["post_id"] = "8099"
    comment = Publication(
        pub_id=comment.pub_id,
        platform=comment.platform,
        source_id=14,
        message_external_id="188801",
        author_id="u1",
        published_at=comment.published_at,
        discovered_at=None,
        url=comment.url,
        text=comment.text,
        parent_id="telegram:14:8099",
        thread_id="telegram:14:8099",
        kind="comment",
        has_media=False,
        metadata={"comment_key": "channel:1:188801", "post_id": "8099"},
    )
    events = [
        {
            "event_id": "e-1400",
            "headline": "ZEC = 1400$",
            "object": "zec",
            "members": [{"publication_id": "telegram:14:8099", "quote": "#zec = 1400$ say GM 🏆"}],
        }
    ]
    link = link_comment(
        comment,
        events,
        theses=[],
        post_observations=[
            {
                "publication_id": "telegram:14:8099",
                "kind": "event",
                "quote": "#zec = 1400$ say GM 🏆",
                "object": "zec",
            }
        ],
    )
    assert link["target"] == "event"
    assert link["target_id"] == "e-1400"
    assert link["basis"]


def test_ecosystem_service_complaint_is_other_subject():
    comment = _pub("tg:1:c1", "Жалоба: NFT-сайт в экосистеме ZEC не открывается", kind="comment")
    comment = Publication(
        pub_id=comment.pub_id,
        platform=comment.platform,
        source_id=1,
        message_external_id="c1",
        author_id="u1",
        published_at=comment.published_at,
        discovered_at=None,
        url=comment.url,
        text=comment.text,
        parent_id="telegram:1:7151",
        thread_id="telegram:1:7151",
        kind="comment",
        has_media=False,
        metadata={},
    )
    events = [
        {
            "event_id": "e-mint",
            "headline": "Минт CypherSquad на ZEC",
            "object": "cyphersquad",
            "members": [
                {"publication_id": "telegram:1:7151", "quote": "минт CypherSquad NFT на ZEC"}
            ],
        }
    ]
    link = link_comment(
        comment,
        events,
        theses=[],
        post_observations=[
            {
                "publication_id": "telegram:1:7151",
                "kind": "event",
                "quote": "минт CypherSquad NFT на ZEC",
            }
        ],
    )
    assert link["target"] == "other_subject"
    assert link["basis"]


def test_cache_identity_omits_cutoff():
    from news_pulse_llm import CLASSIFY_SCHEMA, cache_dir, identity

    item = {"id": "s1", "text": "Zcash vote", "time": "2026-09-18T12:00:00+00:00"}
    a = identity(prompt="p", payload=item, model="m", schema=CLASSIFY_SCHEMA, db_md5="d")
    b = identity(prompt="p", payload=item, model="m", schema=CLASSIFY_SCHEMA, db_md5="d")
    assert "cutoff" not in a
    assert cache_dir(a) == cache_dir(b)


def test_judge_pair_payload_is_unordered():
    from news_pulse_llm import judge_pair_payload

    a = {
        "quote": "A",
        "actor": "x",
        "action": "vote",
        "object": "nu7",
        "qualifiers": {},
        "url": "u1",
    }
    b = {
        "quote": "B",
        "actor": "y",
        "action": "upgrade",
        "object": "nu7",
        "qualifiers": {},
        "url": "u2",
    }
    assert judge_pair_payload(a, b) == judge_pair_payload(b, a)


def test_content_cache_hits_across_cutoffs(tmp_path, monkeypatch):
    from news_pulse_llm import LLMClient

    calls = []

    def fake_call(model, prompt, payload, provider=None):
        calls.append(payload)
        labels = [
            {
                "id": s["id"],
                "kind": "event",
                "origin": "unknown",
                "source_role": "unknown",
                "verification_status": "unverified",
                "quote": "Zcash vote",
                "span": [0, 10],
                "actor": "community",
                "action": "vote",
                "object": "blocks",
                "qualifiers": {},
            }
            for s in payload.get("segments", [])
        ]
        resp = {
            "choices": [{"message": {"content": json.dumps({"labels": labels})}}],
            "usage": {"cost": 0},
        }
        return {"messages": []}, resp, 0.1

    monkeypatch.setattr("news_pulse_llm.call_openrouter", fake_call)
    item = {
        "id": "s1",
        "text": "Zcash vote",
        "mentions": [],
        "kind_hint": "post",
        "url": "https://t.me/ch/1",
        "time": "2026-09-18T12:00:00+00:00",
    }
    c1 = LLMClient(
        cutoff="2026-09-20T00:00:00+00:00", cache_root=tmp_path, db_md5="x", topic="zec", max_usd=1
    )
    c2 = LLMClient(
        cutoff="2026-09-23T00:00:00+00:00", cache_root=tmp_path, db_md5="x", topic="zec", max_usd=1
    )
    assert c1.classify_batch([item])[0]["id"] == "s1"
    assert c2.classify_batch([item])[0]["id"] == "s1"
    assert len(calls) == 1
    assert c2.cache_hits >= 1


def test_write_cache_atomic_leaves_complete_dir(tmp_path):
    from news_pulse_llm import cache_dir, identity, write_cache

    ident = identity(prompt="p", payload={"id": "1"}, model="m", schema="s", db_md5="d")
    write_cache(ident, {"req": 1}, {"choices": []}, 0.1, tmp_path)
    d = cache_dir(ident, tmp_path)
    assert (d / "meta.json").exists()
    assert (d / "request.json").exists()
    assert (d / "response.json").exists()
    leftovers = [
        p
        for p in tmp_path.rglob("*")
        if p.is_file() and (".tmp" in p.name or p.name.startswith("."))
    ]
    assert leftovers == []


def test_action_only_pair_does_not_call_judge():
    called = []

    def judge(a, b):
        called.append((a.obs_id, b.obs_id))
        return "same"

    a = _obs("a", actor=None, action="withdraw", object=None, quote="вывели с биржи")
    b = _obs("b", actor=None, action="withdraw", object=None, quote="другой вывод", pub_id="tg:1:2")
    groups = group_events([a, b], judge=judge)
    assert len(groups) == 2
    assert called == []


def test_large_group_judges_rep_and_last_only():
    members = [
        _obs(
            f"m{i}",
            actor="regulator",
            action="list",
            object="etf",
            qualifiers={"event_date": "2026-09-18"},
            quote=f"unique listing item {['alpha', 'bravo', 'charlie', 'delta', 'echo'][i]}",
            pub_id=f"tg:1:{i}",
            ts=f"2026-09-18T12:0{i}:00",
        )
        for i in range(5)
    ]
    cand = _obs(
        "cand",
        actor="commission",
        action="announce",
        object="equity tokens",
        qualifiers={"event_date": "2026-09-18"},
        quote="SEC announcement on equity tokens",
        pub_id="tg:2:9",
        source_id=2,
        ts="2026-09-18T15:00:00",
    )
    seen: list[tuple[str, str]] = []

    def judge(a, b):
        seen.append((a.obs_id, b.obs_id))
        return "same"

    groups = group_events([*members, cand], judge=judge)
    judged = set()
    for x, y in seen:
        judged.add(y if x == "cand" else x if y == "cand" else "")
    judged.discard("")
    assert judged <= {"m0", "m4"}
    assert "m0" in judged
    assert any("cand" in g and len(g) > 1 for g in ({m.obs_id for m in g.members} for g in groups))


def test_llm_request_never_contains_records_outside_window(tmp_path, monkeypatch):
    from news_pulse_build import build

    path = _tiny_db(tmp_path / "w.db")
    db = __import__("sqlite3").connect(path)
    for eid, ts, text in (
        ("1", "2026-09-19 23:59:59.000000", "Zcash inside last day"),
        ("2", "2026-09-20 00:00:00.000000", "Zcash after window"),
        ("3", "2026-09-18 10:00:00.000000", "Zcash mid window"),
        ("4", "2026-09-16 23:59:59.000000", "Zcash before window"),
    ):
        payload = json.dumps(
            {
                "text": text,
                "timestamp": ts.replace(" ", "T") + "+00:00",
                "channel_ref": "@ch",
                "link": f"https://t.me/ch/{eid}",
                "external_id": eid,
            }
        )
        db.execute("UPDATE raw_item SET payload=? WHERE external_id=?", (payload, eid))
    db.commit()
    db.close()
    captured: list[dict] = []

    def fake_call(model, prompt, payload, provider=None):
        captured.append(payload)
        if "segments" in payload:
            labels = [
                {
                    "id": s["id"],
                    "kind": "event",
                    "origin": "unknown",
                    "source_role": "unknown",
                    "verification_status": "unverified",
                    "quote": (s.get("text") or "x")[:20],
                    "span": [0, min(20, len(s.get("text") or "x"))],
                    "actor": "zcash",
                    "action": "note",
                    "object": "zec",
                    "qualifiers": {},
                }
                for s in payload["segments"]
            ]
            content = json.dumps({"labels": labels})
        elif "pairs" in payload:
            content = json.dumps(
                {"pairs": [{"id": p["id"], "decision": "different"} for p in payload["pairs"]]}
            )
        else:
            content = json.dumps({"decision": "different"})
        return {}, {"choices": [{"message": {"content": content}}], "usage": {"cost": 0}}, 0.0

    monkeypatch.setattr("news_pulse_llm.call_openrouter", fake_call)
    build(
        path, "zec", "2026-09-17..2026-09-19", write=False, cache_root=tmp_path / "cache", max_usd=1
    )
    forbidden = ("Zcash after window", "future comment")
    current_end = _dt("2026-09-20T00:00:00")
    for payload in captured:
        texts = []
        times = []
        for seg in payload.get("segments") or []:
            texts.append(seg.get("text") or "")
            if seg.get("time"):
                times.append(_dt(str(seg["time"])[:19]))
        for row in [payload.get("a"), payload.get("b"), *(payload.get("pairs") or [])]:
            if not isinstance(row, dict):
                continue
            for side in (row, row.get("a") or {}, row.get("b") or {}):
                texts.append(str(side.get("quote") or side.get("text") or ""))
                if side.get("time"):
                    times.append(_dt(str(side["time"])[:19]))
        assert all(bad not in t for t in texts for bad in forbidden)
        assert all(t < current_end for t in times)


def test_classify_and_judge_batches_keep_input_order(tmp_path, monkeypatch):
    from news_pulse_llm import LLMClient

    def fake_call(model, prompt, payload, provider=None):
        if "segments" in payload:
            labels = list(
                reversed(
                    [
                        {
                            "id": s["id"],
                            "kind": "event",
                            "origin": "unknown",
                            "source_role": "unknown",
                            "verification_status": "unverified",
                            "quote": s["id"],
                            "span": [0, 1],
                            "actor": None,
                            "action": None,
                            "object": None,
                            "qualifiers": {},
                        }
                        for s in payload["segments"]
                    ]
                )
            )
            content = json.dumps({"labels": labels})
        else:
            content = json.dumps(
                {
                    "pairs": list(
                        reversed(
                            [
                                {"id": p["id"], "decision": "different"}
                                for p in payload.get("pairs", [])
                            ]
                        )
                    )
                }
            )
        return {}, {"choices": [{"message": {"content": content}}], "usage": {"cost": 0}}, 0.0

    monkeypatch.setattr("news_pulse_llm.call_openrouter", fake_call)
    client = LLMClient(cache_root=tmp_path, db_md5="x", topic="zec", max_usd=1)
    items = [
        {
            "id": f"s{i}",
            "text": f"t{i}",
            "mentions": [],
            "kind_hint": "post",
            "url": "",
            "time": "t",
        }
        for i in range(3)
    ]
    labels = client.classify_batch(items, batch_size=12)
    assert [x["id"] for x in labels] == ["s0", "s1", "s2"]
    pairs = [
        (
            {
                "quote": "a",
                "actor": None,
                "action": "x",
                "object": "o",
                "qualifiers": {},
                "url": "u1",
            },
            {
                "quote": "b",
                "actor": None,
                "action": "y",
                "object": "o",
                "qualifiers": {},
                "url": "u2",
            },
        ),
        (
            {
                "quote": "c",
                "actor": None,
                "action": "x",
                "object": "p",
                "qualifiers": {},
                "url": "u3",
            },
            {
                "quote": "d",
                "actor": None,
                "action": "y",
                "object": "p",
                "qualifiers": {},
                "url": "u4",
            },
        ),
    ]
    assert client.judge_many(pairs) == ["different", "different"]


def test_amount_units_normalize_to_million_usd():
    from news_pulse_events import parse_amount_musd

    assert parse_amount_musd("ETH ETF: отток $224M") == pytest.approx(224)
    assert parse_amount_musd("отток спотовых ETH-ETF составил $224,1 млн") == pytest.approx(224.1)
    assert parse_amount_musd("#ETH = +$269,980,000") == pytest.approx(269.98)
    assert parse_amount_musd("приток ~$1,2 млрд") == pytest.approx(1200)


def test_daily_etf_report_next_morning_merges_with_rounded_amount():
    wordy = _obs(
        "wordy",
        actor=None,
        action="чистый приток",
        object="спотовые ETH-ETF",
        qualifiers={"date": "вчера"},
        quote="Вчера общий чистый приток спотовых ETH-ETF составил $143,7 млн.",
        ts="2026-09-19T08:00:00",
        pub_id="tg:1:1",
    )
    table = _obs(
        "table",
        actor=None,
        action="inflow",
        object="ETH ETF",
        qualifiers={"amount": "$144M", "event_date": "2026-09-19"},
        quote="📈 🟢 ETH ETF: приток $144M",
        ts="2026-09-19T09:00:00",
        pub_id="tg:2:1",
        source_id=2,
    )
    groups = group_events([wordy, table])
    assert len(groups) == 1


def test_btc_and_eth_etf_flows_stay_apart_and_next_day_differs():
    eth = _obs(
        "eth",
        actor=None,
        action="inflow",
        object="ETH ETF",
        quote="ETH ETF: приток $144M",
        qualifiers={"event_date": "2026-09-19"},
        pub_id="tg:1:1",
    )
    btc = _obs(
        "btc",
        actor=None,
        action="inflow",
        object="BTC ETF",
        quote="BTC ETF: приток $144M",
        qualifiers={"event_date": "2026-09-19"},
        pub_id="tg:2:1",
        source_id=2,
    )
    next_day = _obs(
        "next",
        actor=None,
        action="inflow",
        object="ETH ETF",
        quote="ETH ETF: приток $270M",
        qualifiers={"event_date": "2026-09-20"},
        pub_id="tg:3:1",
        source_id=3,
    )
    groups = group_events([eth, btc, next_day])
    assert len(groups) == 3


def test_etf_flow_table_rows_are_candidates_with_header_context():
    topic = load_aliases("docs/research/entity_aliases.tsv")["eth"]
    pub = _pub(
        "telegram:1:12",
        "🧐 SV: Финпотоки крипто-ETF за вчерашний день.\n\n"
        "▫️#BTC = +$998,950,000.\n▫️#ETH = +$269,980,000.\n",
    )
    segs = segment_publication(pub, topic)
    eth = [s for s in segs if "#ETH" in s.text]
    assert eth and eth[0].is_candidate and eth[0].role == "body"
    assert "ETF" in eth[0].context
    assert not any("#BTC" in s.text and "#ETH" in s.text for s in segs)


def test_same_etf_amount_days_apart_is_not_one_event():
    early = _obs(
        "early",
        actor=None,
        action="outflow",
        object="спотовые ETH-ETF",
        quote="Общий чистый отток спотовых ETH-ETF составил $142,3 млн.",
        ts="2026-09-16T04:03:01",
    )
    late = _obs(
        "late",
        actor=None,
        action="outflow",
        object="спотовые ETH-ETF",
        quote="Общий чистый отток спотовых ETH-ETF составил ~$140 млн.",
        ts="2026-09-21T03:53:01",
        pub_id="tg:1:2",
    )
    assert len(group_events([early, late])) == 2


def test_flow_table_row_uses_header_for_fund_object():
    from news_pulse_events import subject_key

    row = _obs(
        "row",
        actor=None,
        action="финпотоки",
        object="ETH",
        quote="#ETH = +$269,980,000 (максимум с октября прошлого года).",
    )
    row.context = "🧐 SV: Финпотоки крипто-ETF за вчерашний день."
    assert subject_key(row)[2] == "eth_etf"


def test_flow_table_row_merges_with_daily_report():
    row = _obs(
        "row",
        actor=None,
        action="финпотоки",
        object="ETH",
        qualifiers={"event_date": "2026-09-22"},
        quote="#ETH = +$269,980,000 (максимум с октября прошлого года).",
        ts="2026-09-22T13:10:11",
    )
    row.context = "🧐 SV: Финпотоки крипто-ETF за вчерашний день."
    report = _obs(
        "report",
        actor=None,
        action="общий чистый приток спотовых ETH-ETF составил",
        object="$270 млн",
        quote="Общий чистый приток спотовых ETH-ETF составил $270 млн.",
        ts="2026-09-22T04:00:00",
        pub_id="tg:2:1",
        source_id=2,
    )
    assert len(group_events([row, report])) == 1


def test_topic_as_context_does_not_become_topic_event():
    from news_pulse_build import observations_for_events

    base = {
        "publication_id": "telegram:1:13",
        "source_id": 1,
        "author_id": None,
        "published_at": _dt("2026-09-19T08:54:34"),
        "url": "https://t.me/ch/13",
        "span": (0, 36),
        "kind": "event",
        "actor": None,
        "action": "вырос",
        "object": "ZAMA",
        "qualifiers": {},
        "origin": "retelling",
        "source_role": "editorial",
        "verification_status": "unverified",
        "topic_mentions": [{"text": "ZEC", "status": "confirmed"}],
        "status": "ok",
    }
    ctx = Observation(
        obs_id="c", quote="Grok 4.6 оказался прав: ZEC король?", topic_role="context", **base
    )
    subj = Observation(obs_id="s", quote="ZEC вырос на 20%", **base)
    assert [o.obs_id for o in observations_for_events([ctx, subj])] == ["s"]


def test_off_topic_thread_comments_stay_out_of_discussion():
    from dataclasses import replace

    from news_pulse_build import _process_window
    from news_pulse_load import Snapshot, parse_window

    topic = load_aliases("docs/research/entity_aliases.tsv")["zec"]
    on_post = _pub("telegram:1:1", "Zcash сообщество проголосовало за блоки 25 секунд")
    off_post = _pub("telegram:1:2", "NFT коллекция DUCKZ открыла вайтлист")
    on_c = replace(
        _pub("telegram:1:1:c:1", "а когда хардфорк?", kind="comment"), thread_id="telegram:1:1"
    )
    off_c = replace(_pub("telegram:1:2:c:2", "Скам же", kind="comment"), thread_id="telegram:1:2")
    named = replace(
        _pub("telegram:1:2:c:3", "лучше бы ZEC купил", kind="comment"), thread_id="telegram:1:2"
    )
    snap = Snapshot(
        window=parse_window("2026-09-18..2026-09-18"),
        cutoff=_dt("2026-09-19T00:00:00"),
        db_md5="x",
        sources={},
        publications=[on_post, off_post],
        comments=[on_c, off_c, named],
        dropped_after_cutoff=0,
    )
    *_, discussion, _links = _process_window(snap, topic, None)
    urls = {row.get("url") for row in discussion}
    assert off_c.url not in urls
    assert named.url in urls


def test_long_headline_is_clipped_at_word_boundary_without_splitting_numbers():
    from news_pulse_events import HEADLINE_LIMIT, clip_headline

    quote = "а" * 170 + " убыток ~$26–30 млн и дальше текст"
    head = clip_headline(quote)
    assert head.endswith("…")
    assert len(head) <= HEADLINE_LIMIT + 1
    assert "~$2" not in head
    assert quote.startswith(head[:-1])
    assert clip_headline("коротко\nвторая строка") == "коротко"


def test_grounding_check_catches_altered_number_and_edited_brief(tmp_path):
    from news_pulse_build import render_markdown
    from news_pulse_ground import check_run

    source = "Фонд привлёк $12 млн.\nВторая строка поста."
    url = "https://t.me/ch/1"
    member = {
        "publication_id": "p1",
        "source_id": 1,
        "url": url,
        "quote": "Фонд привлёк $12 млн.",
        "origin": "own",
    }
    counts = {
        "events": 1,
        "publications": 1,
        "channels": 1,
        "found_origins": 1,
        "reprints": 0,
        "unknown_origin": 0,
    }
    pulse = {
        "topic": "x",
        "window": {"requested": "2026-09-01..2026-09-02"},
        "status": "ok",
        "events": [
            {
                "event_id": "e1",
                "headline": "Фонд привлёк $12 млн.",
                "counts": counts,
                "members": [member],
            }
        ],
        "distribution_and_positions": [],
        "discussion": [],
        "changes": {},
        "short_observations": [],
        "coverage": {},
        "limitations": [],
        "evidence": [{"url": url, "quote": "Фонд привлёк $12 млн."}],
    }

    def write(p, brief=None):
        run = tmp_path / str(len(list(tmp_path.iterdir())))
        run.mkdir()
        (run / "pulse.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        (run / "brief.md").write_text(
            brief if brief is not None else render_markdown(p), encoding="utf-8"
        )
        return run

    texts = {url: source}
    ok = check_run(write(pulse), texts)
    assert ok["grounded"] == ok["claims"]

    bad = json.loads(json.dumps(pulse))
    bad["events"][0]["members"][0]["quote"] = "Фонд привлёк $15 млн."
    report = check_run(write(bad), texts)
    assert report["fabricated_numbers"] == 1

    edited = check_run(write(pulse, render_markdown(pulse) + "\nДобавлено вручную.\n"), texts)
    assert any(f["kind"] == "render" for f in edited["failures"])

    wrong_count = json.loads(json.dumps(pulse))
    wrong_count["events"][0]["counts"]["publications"] = 3
    assert any(f["kind"] == "counts" for f in check_run(write(wrong_count), texts)["failures"])


def test_topic_thread_comment_without_ticker_stays_topic_level():
    from dataclasses import replace

    from news_pulse_build import _process_window
    from news_pulse_load import Snapshot, parse_window

    topic = load_aliases("docs/research/entity_aliases.tsv")["eth"]
    post = _pub("telegram:1:1", "Ethereum update вышел в тестнет")
    doubt = replace(
        _pub("telegram:1:1:c:1", "Не понимаю, зачем это нужно", kind="comment"),
        thread_id="telegram:1:1",
    )
    snap = Snapshot(
        window=parse_window("2026-09-18..2026-09-18"),
        cutoff=_dt("2026-09-19T00:00:00"),
        db_md5="x",
        sources={},
        publications=[post],
        comments=[doubt],
        dropped_after_cutoff=0,
    )
    *_, discussion, _links = _process_window(snap, topic, None)
    rows = [row for row in discussion if row.get("url") == doubt.url]
    assert rows and rows[0]["target"] == "topic_level"


def test_changes_count_topic_discussion_not_all_snapshot_comments():
    from news_pulse_build import _changes
    from news_pulse_load import Snapshot, parse_window

    def snap(window, posts, comments):
        return Snapshot(
            window=parse_window(window),
            cutoff=_dt("2026-09-24T00:00:00"),
            db_md5="x",
            sources={},
            publications=posts,
            comments=comments,
            dropped_after_cutoff=0,
        )

    noise = [_pub(f"telegram:9:{i}", "шум", kind="comment", source_id=9) for i in range(5)]
    cur = snap("2026-09-22..2026-09-23", [_pub("telegram:1:1", "Aave", source_id=1)], noise)
    prev = snap("2026-09-20..2026-09-21", [_pub("telegram:2:1", "Aave", source_id=2)], noise[:3])
    topic_row = {"url": "https://t.me/ch/c1", "target": "topic_level"}
    changes = _changes(
        cur, prev, events=[], prev_events=[], discussion=[topic_row], prev_discussion=[]
    )
    assert changes["topic_comments"] == 1
    assert changes["previous_topic_comments"] == 0
    assert "discussion_comments" not in changes
    assert changes["source_coverage"]["added_channels"] == ["1"]
    assert changes["source_coverage"]["removed_channels"] == ["2"]
    md = render_markdown(
        build_from_parts(
            topic="aave",
            window="2026-09-22..2026-09-23",
            events=[],
            positions=[],
            discussion=[],
            changes=changes,
            coverage={"publications": 1, "comments": 5, "channels": 1},
            limitations=[],
            evidence=[],
        )
    )
    assert "Комментарии в текущем окне" not in md
    assert "Комментарии по теме: 1 в текущем окне, 0 в предыдущем." in md


def test_identical_text_on_different_days_is_not_one_event():
    kw = {
        "actor": None,
        "action": "inflow",
        "object": "ETH ETF",
        "quote": "Today ETH-ETF inflow $100M",
    }
    a = _obs("a", ts="2026-09-21T10:00:00", **kw)
    b = _obs("b", ts="2026-09-23T10:00:00", pub_id="tg:1:2", **kw)
    assert a.text_hash == b.text_hash
    assert len(group_events([a, b])) == 2


def test_explicit_consecutive_flow_days_with_close_amounts_stay_apart():
    a = _obs(
        "a",
        actor=None,
        action="inflow",
        object="ETH ETF",
        qualifiers={"event_date": "2026-09-21"},
        quote="ETH ETF: приток $100M",
        ts="2026-09-22T09:00:00",
    )
    b = _obs(
        "b",
        actor=None,
        action="inflow",
        object="ETH ETF",
        qualifiers={"event_date": "2026-09-22"},
        quote="ETH ETF: приток $102M",
        ts="2026-09-23T09:00:00",
        pub_id="tg:2:1",
        source_id=2,
    )
    assert len(group_events([a, b])) == 2


def test_same_action_object_with_different_actors_stays_apart():
    binance = _obs(
        "a", actor="Binance", action="listing", object="AAVE", quote="Binance listing AAVE"
    )
    coinbase = _obs(
        "b",
        actor="Coinbase",
        action="listing",
        object="AAVE",
        quote="Coinbase listing AAVE",
        pub_id="tg:2:1",
        source_id=2,
    )
    assert len(group_events([binance, coinbase])) == 2


@pytest.mark.parametrize(("amount_a", "amount_b"), [("$100M", "$100M"), ("$143.7M", "$144M")])
def test_explicit_different_days_stay_apart_even_with_equal_or_rounded_amounts(amount_a, amount_b):
    a = _obs(
        "a",
        actor=None,
        action="inflow",
        object="ETH ETF",
        qualifiers={"event_date": "2026-09-21"},
        quote=f"ETH ETF 21 сентября: приток {amount_a}",
        ts="2026-09-22T09:00:00",
    )
    b = _obs(
        "b",
        actor=None,
        action="inflow",
        object="ETH ETF",
        qualifiers={"event_date": "2026-09-22"},
        quote=f"ETH ETF 22 сентября: приток {amount_b}",
        ts="2026-09-23T09:00:00",
        pub_id="tg:2:1",
        source_id=2,
    )
    assert len(group_events([a, b])) == 2


def test_classifier_dates_that_are_not_publication_days_are_explicit():
    # neither date equals its publication day, so both are event dates, not report days
    a = _obs(
        "a",
        actor=None,
        action="inflow",
        object="ETH ETF",
        qualifiers={"event_date": "2026-09-21"},
        quote="ETH ETF: приток $100M",
    )
    b = _obs(
        "b",
        actor=None,
        action="inflow",
        object="ETH ETF",
        qualifiers={"event_date": "2026-09-22"},
        quote="ETH ETF: приток $100M",
        pub_id="tg:2:1",
        source_id=2,
    )
    assert len(group_events([a, b])) == 2


def test_different_actors_stay_apart_when_objects_are_aliases():
    binance = _obs(
        "a", actor="Binance", action="listing", object="ZEC", quote="Binance listing ZEC"
    )
    coinbase = _obs(
        "b",
        actor="Coinbase",
        action="listing",
        object="Zcash",
        quote="Coinbase listing Zcash",
        pub_id="tg:2:1",
        source_id=2,
    )
    assert len(group_events([binance, coinbase])) == 2


def test_different_actors_go_to_the_judge_not_to_a_veto():
    binance = _obs(
        "a", actor="Binance", action="listing", object="ZEC", quote="Binance listing ZEC"
    )
    coinbase = _obs(
        "b",
        actor="Coinbase",
        action="listing",
        object="Zcash",
        quote="Coinbase listing Zcash",
        pub_id="tg:2:1",
        source_id=2,
    )
    company = _obs(
        "c",
        actor="BitMine",
        action="acquire",
        object="ETH",
        quote="BitMine bought ETH",
    )
    ticker = _obs(
        "d",
        actor="$BMNR",
        action="acquire",
        object="$ETH",
        quote="$BMNR bought $ETH",
        pub_id="tg:2:1",
        source_id=2,
    )
    asked = []

    def judge(a, b):
        asked.append({a.obs_id, b.obs_id})
        return "same" if {a.obs_id, b.obs_id} == {"c", "d"} else "different"

    assert len(group_events([binance, coinbase], judge=judge)) == 2
    assert len(group_events([company, ticker], judge=judge)) == 1
    assert {"c", "d"} in asked


def test_digest_items_with_different_actors_stay_apart():
    wizards = _obs(
        "a",
        actor="Shielded Wizards",
        action="mint",
        object="ZEC",
        quote="• Shielded Wizards: 2,100 · 0.001 ZEC · 21 сен 20:00 МСК",
    )
    bitfoots = _obs(
        "b",
        actor="BITFOOTS",
        action="mint",
        object="ZEC",
        quote="• BITFOOTS: 303 1/1 · $5 в ZEC · заявки до 21 сен 17:00 МСК",
    )
    assert len(group_events([wizards, bitfoots])) == 2


def test_same_short_quote_from_different_actors_is_not_one_event():
    bet = _obs("a", actor="гигачад", action="сделал ставки", object="ZEC", quote="ZEC")
    lost = _obs(
        "b", actor="Я", action="не шарю", object="ZEC", quote="ZEC", pub_id="tg:2:1", source_id=2
    )
    assert len(group_events([bet, lost])) == 2


def test_grounding_checks_short_observations_and_discussion_basis(tmp_path):
    from news_pulse_ground import check_run

    source = "Фонд привлёк $12 млн.\nВторая строка поста."
    comment = "Не понимаю, зачем это нужно"
    url, curl = "https://t.me/ch/1", "https://t.me/ch/1?comment=2"
    member = {
        "publication_id": "p1",
        "source_id": 1,
        "url": url,
        "quote": "Фонд привлёк $12 млн.",
        "origin": "own",
    }
    pulse = build_from_parts(
        topic="x",
        window="2026-09-01..2026-09-02",
        events=[
            {
                "event_id": "e1",
                "headline": "Фонд привлёк $12 млн.",
                "counts": {
                    "events": 1,
                    "publications": 1,
                    "channels": 1,
                    "found_origins": 1,
                    "reprints": 0,
                    "unknown_origin": 0,
                },
                "members": [member],
            }
        ],
        positions=[],
        discussion=[
            {
                "target": "topic_level",
                "target_id": None,
                "text": comment,
                "basis": "совпадение темы недостаточно, связь со событием не установлена",
                "url": curl,
                "quote": comment,
            }
        ],
        changes={},
        coverage={},
        limitations=[],
        evidence=[],
    )
    texts = {url: source, curl: comment}

    def run_of(p):
        p = json.loads(json.dumps(p))
        p["brief_markdown"] = render_markdown(p)
        run = tmp_path / str(len(list(tmp_path.iterdir())))
        run.mkdir()
        (run / "pulse.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        (run / "brief.md").write_text(p["brief_markdown"], encoding="utf-8")
        return check_run(run, texts)

    ok = run_of(pulse)
    assert ok["grounded"] == ok["claims"], ok["failures"]

    fake = json.loads(json.dumps(pulse))
    fake["short_observations"] = ["Aave officially confirmed a price of $987654321."]
    report = run_of(fake)
    assert any(f["kind"] == "short_observation" for f in report["failures"])

    basis = json.loads(json.dumps(pulse))
    basis["discussion"][0]["basis"] = "автор подтвердил, что это реакция на событие"
    assert any(f["kind"] == "discussion_basis" for f in run_of(basis)["failures"])

    target = json.loads(json.dumps(pulse))
    target["discussion"][0].update(target="event", target_id="e404")
    assert any(f["kind"] == "discussion_basis" for f in run_of(target)["failures"])

    # the basis is re-derived from the source, not only matched against the template list
    repeats = json.loads(json.dumps(pulse))
    repeats["discussion"][0].update(
        target="event", target_id="e1", basis="комментарий повторяет формулировку события"
    )
    assert any(f["kind"] == "discussion_basis" for f in run_of(repeats)["failures"])

    no_id = json.loads(json.dumps(repeats))
    no_id["discussion"][0].update(target_id=None, text="Фонд привлёк $12 млн.")
    texts[curl] = "Фонд привлёк $12 млн."
    assert any(f["kind"] == "discussion_basis" for f in run_of(no_id)["failures"])

    # under the post, but "Не понимаю, зачем это нужно" is not about the raise
    under_post = json.loads(json.dumps(pulse))
    under_post["discussion"][0].update(
        target="event",
        target_id="e1",
        basis="реплика к посту с одним событием по теме и тому же предмету",
    )
    texts[curl] = comment
    assert any(f["kind"] == "discussion_basis" for f in run_of(under_post)["failures"])
    about = "Фонд теперь купит, цена пойдёт вверх"
    texts[curl] = about
    under_post["discussion"][0].update(text=about, quote=about)
    assert not run_of(under_post)["failures"]
    elsewhere = json.loads(json.dumps(under_post))
    elsewhere["discussion"][0]["url"] = "https://t.me/other/7?comment=2"
    texts["https://t.me/other/7?comment=2"] = about
    assert any(f["kind"] == "discussion_basis" for f in run_of(elsewhere)["failures"])
    two = json.loads(json.dumps(under_post))
    two["events"].append(dict(two["events"][0], event_id="e2"))
    assert any(f["kind"] == "discussion_basis" for f in run_of(two)["failures"])


def test_long_comment_is_clipped_without_splitting_numbers():
    text = "держу етф " + "x" * 228 + " 100 и 200 канал"
    link = link_comment(_pub("tg:1:c9", text, kind="comment"), [], theses=[], post_observations=[])
    assert link["text"].endswith("x") and text.startswith(link["text"])
    assert "1" not in link["text"]
