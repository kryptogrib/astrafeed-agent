"""Read published snapshots. HTTP never triggers LLM or collection."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from astrafeed.application.agenda_changes import compare_snapshots
from astrafeed.application.agenda_markdown import render_agenda_md, render_story_md
from astrafeed.application.agenda_text import source_group
from astrafeed.domain.agenda import (
    SEARCH_DEFAULT_LIMIT,
    SEARCH_MAX_LIMIT,
    CycleState,
    SearchDoc,
    SearchHit,
    Snapshot,
    StoryCard,
    StoryDetail,
    is_stale,
)
from astrafeed.ports.agenda import AgendaStore


class AgendaPreparing(Exception):
    """No snapshot has been published yet."""


class AgendaNotFound(Exception):
    """Unknown snapshot or story in the requested snapshot."""


def _status(snapshot: Snapshot, now: datetime) -> dict:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "t": snapshot.t.isoformat(),
        "collected_at": snapshot.collected_at.isoformat(),
        "analyzed_at": snapshot.analyzed_at.isoformat(),
        "published_at": snapshot.published_at.isoformat(),
        "stale": is_stale(snapshot.published_at, now),
        "snapshot_age_seconds": max(0, int((now - snapshot.published_at).total_seconds())),
        "coverage": {
            "channels_ok": snapshot.coverage.channels_ok,
            "channels_failed": snapshot.coverage.channels_failed,
            "channels_incomplete": snapshot.coverage.channels_incomplete,
            "publications_total": snapshot.coverage.publications_total,
            "publications_processed": snapshot.coverage.publications_processed,
            "publications_queued": snapshot.coverage.publications_queued,
            "comparable_channels": snapshot.coverage.comparable_channels,
        },
        "queue_depth": snapshot.queue_depth,
        "limitations": list(snapshot.limitations),
        "agenda_mode": snapshot.agenda_mode,
    }


def _card_payload(card: StoryCard) -> dict:
    return {
        "story_id": card.story_id,
        "title": card.title,
        "entities": list(card.entities),
        "current_channels": card.current_channels,
        "previous_channels": card.previous_channels,
        "growth": card.growth,
        "growth_null_reason": card.growth_null_reason,
        "first_seen": card.first_seen.isoformat(),
        "explanation": card.explanation,
        "claims": [
            {
                "kind": claim.kind,
                "speaker": claim.speaker,
                "quote": claim.quote,
                "paraphrase_ru": claim.paraphrase_ru,
                "translation": claim.translation,
                "link": claim.link,
                "channel": claim.channel_ref,
            }
            for claim in card.claims
        ],
        "discussion": _discussion_payload(card),
        "signals": _signals_payload(card),
    }


def _signals_payload(card: StoryCard) -> dict | None:
    signals = card.signals
    if signals is None:
        return None
    price = signals.price
    caveat = signals.caveat_drop
    return {
        "independent_channels": signals.independent_channels,
        "echo_channels": signals.echo_channels,
        "spread_minutes": signals.spread_minutes,
        "confirmation": signals.confirmation,
        "attributed_to": list(signals.attributed_to),
        "figures": [
            {"text": figure.text, "usd": figure.usd, "channels": list(figure.channels)}
            for figure in signals.figures
        ],
        "figures_conflict": signals.figures_conflict,
        "tickers": list(signals.tickers),
        "official_after_minutes": next(
            (
                node.minutes_after_first
                for node in signals.sources
                if node.sourcing == "official" and node.minutes_after_first > 0
            ),
            None,
        ),
        "sources": [
            {
                "channel": node.channel_ref,
                "link": node.link,
                "published_at": node.published_at.isoformat(),
                "minutes_after_first": node.minutes_after_first,
                "echo_of": node.echo_of or None,
                "sourcing": node.sourcing,
            }
            for node in signals.sources
        ],
        "caveat_drop": None
        if caveat is None
        else {
            "qualifier": caveat.qualifier,
            "before_channel": caveat.before_channel,
            "before_link": caveat.before_link,
            "before_quote": caveat.before_quote,
            "after_channel": caveat.after_channel,
            "after_link": caveat.after_link,
            "after_quote": caveat.after_quote,
            "minutes_later": caveat.minutes_later,
        },
        "price": None
        if price is None
        else {
            "inst_id": price.inst_id,
            "since": price.since.isoformat(),
            "price_then": price.price_then,
            "price_now": price.price_now,
            "change_pct": price.change_pct,
            "measured_at": price.measured_at.isoformat(),
            "price_hour_before": price.price_hour_before,
            "change_pct_before": price.change_pct_before,
            "verdict": price.verdict,
            "at_posts": [
                {
                    "channel": point.channel_ref,
                    "published_at": point.published_at.isoformat(),
                    "price": point.price,
                    "move_done_pct": point.move_done_pct,
                }
                for point in price.at_posts
            ],
            "source": "OKX spot",
        },
    }


def _discussion_payload(card: StoryCard) -> dict | None:
    discussion = card.discussion
    if discussion is None:
        return None
    return {
        "comment_count": discussion.comment_count,
        "read_count": discussion.read_count,
        "points": list(discussion.points),
        "highlights": list(discussion.highlights),
        "quotes": [
            {
                "text": quote.text,
                "translation": quote.translation,
                "link": quote.link,
                "channel": quote.channel_ref,
            }
            for quote in discussion.quotes
        ],
    }


def _detail_payload(detail: StoryDetail) -> dict:
    payload = _card_payload(detail.card)
    payload.update(
        {
            "events": [
                {
                    "event_id": event.event_id,
                    "when": event.when,
                    "amount": event.amount,
                    "participants": list(event.participants),
                }
                for event in detail.events
            ],
            "positions": [
                {
                    "speaker": position.speaker,
                    "channel": position.channel_ref,
                    "quote": position.quote,
                    "paraphrase_ru": position.paraphrase_ru,
                    "translation": position.translation,
                    "link": position.link,
                }
                for position in detail.positions
            ],
            "publications": [
                {
                    "publication_id": pub.publication_id,
                    "channel": pub.channel_ref,
                    "link": pub.link,
                    "published_at": pub.published_at.isoformat(),
                    "quote": pub.quote,
                }
                for pub in detail.publications
            ],
        }
    )
    return payload


def _recent_source_posts(snapshot: Snapshot) -> dict[str, list[dict]]:
    """Show source activity without promoting one-source posts into the agenda."""
    cutoff = snapshot.t - timedelta(hours=24)
    candidates: dict[str, list[tuple[datetime, str, dict]]] = {"x": [], "reddit": []}
    seen_ids: set[str] = set()
    for detail in snapshot.stories.values():
        title = detail.card.title
        if not detail.events or re.search(
            r"\b(?:daily|day\s+\d+|user asks|anybody know)\b|\?", title, re.I
        ):
            continue
        for pub in detail.publications:
            group = source_group(pub.channel_ref, pub.link)
            source = {"X": "x", "Reddit": "reddit"}.get(group)
            if (
                source is None
                or pub.publication_id in seen_ids
                or not cutoff <= pub.published_at <= snapshot.t
            ):
                continue
            seen_ids.add(pub.publication_id)
            candidates[source].append(
                (
                    pub.published_at,
                    pub.publication_id,
                    {
                        "channel": pub.channel_ref,
                        "link": pub.link,
                        "published_at": pub.published_at.isoformat(),
                        "title": detail.card.title,
                        "text": " ".join((pub.quote or detail.card.title).split())[:240],
                    },
                )
            )
    result: dict[str, list[dict]] = {}
    for source, posts in candidates.items():
        chosen: list[dict] = []
        channel_counts: dict[str, int] = {}
        per_channel = 1 if source == "x" else 2
        for _, _, post in sorted(posts, key=lambda item: (item[0], item[1]), reverse=True):
            channel = post["channel"]
            if channel_counts.get(channel, 0) >= per_channel:
                continue
            channel_counts[channel] = channel_counts.get(channel, 0) + 1
            chosen.append(post)
            if len(chosen) == 3:
                break
        result[source] = chosen
    return result


def search_in_snapshot(
    snapshot: Snapshot, query: str, *, limit: int, offset: int
) -> tuple[list[SearchHit], int]:
    q = query.strip()
    limit = max(1, min(limit, SEARCH_MAX_LIMIT))
    offset = max(0, offset)
    if not q:
        return [], 0
    needle = q.casefold()
    query_terms = {_search_term(token) for token in re.findall(r"[\w]+", needle)}
    query_terms.discard("")
    if not query_terms:
        return [], 0
    scored: list[SearchHit] = []
    docs_by_story: dict[str, list] = {}
    for doc in snapshot.search_docs:
        docs_by_story.setdefault(doc.story_id, []).append(doc)
    display_titles = {card.story_id: card.title for card in (*snapshot.agenda, *snapshot.upcoming)}
    for story_id, docs in docs_by_story.items():
        title = next((doc.text for doc in docs if doc.kind == "title"), story_id)
        display_title = display_titles.get(story_id, title)
        if display_title != title:
            docs = [*docs, SearchDoc(story_id, "title", display_title)]
        matches: list[str] = []
        found: set[str] = set()
        score = 0.0
        for doc in docs:
            terms = {_search_term(token) for token in re.findall(r"[\w]+", doc.text.casefold())}
            overlap = terms & query_terms
            if overlap:
                found.update(overlap)
                weight = {
                    "title": 10.0,
                    "entity": 4.0,
                    "alias": 3.0,
                    "claim": 2.0,
                    "publication": 1.0,
                }[doc.kind]
                score += weight * len(overlap)
                if len(matches) < 3:
                    matches.append(doc.text[:250])
        if len(found) < min(2, len(query_terms)):
            continue
        score += 100.0 * len(found) / len(query_terms)
        if title.casefold() == needle:
            score += 1000.0
        elif needle in title.casefold():
            score += 20.0
        scored.append(SearchHit(story_id, display_title, tuple(matches), score))
    scored.sort(key=lambda hit: (-hit.score, hit.story_id))
    return scored[offset : offset + limit], len(scored)


def _search_term(token: str) -> str:
    """Small deterministic Russian inflection fold for evidence search."""
    if re.fullmatch(r"[а-яё]+", token):
        return token[:4] if len(token) >= 5 else token
    return token


async def load_snapshot(store: AgendaStore, snapshot_id: str | None) -> Snapshot:
    snapshot = await store.get_snapshot(snapshot_id)
    if snapshot is None and snapshot_id is None:
        raise AgendaPreparing("preparing")
    if snapshot is None:
        raise AgendaNotFound(f"unknown snapshot {snapshot_id}")
    return snapshot


async def agenda_payload(
    store: AgendaStore,
    *,
    snapshot_id: str | None,
    now: datetime,
    since_snapshot_id: str | None = None,
) -> dict:
    if since_snapshot_id is not None and not since_snapshot_id.strip():
        raise ValueError("since_snapshot_id must not be blank")
    snapshot = await load_snapshot(store, snapshot_id)
    payload = _status(snapshot, now)
    payload["stories"] = [_card_payload(card) for card in snapshot.agenda]
    payload["source_posts"] = _recent_source_posts(snapshot)
    payload["upcoming"] = [_card_payload(card) for card in snapshot.upcoming]
    payload["lead_channels"] = [
        {
            "channel": lead.channel_ref,
            "stories_first": lead.stories_first,
            "median_lead_minutes": lead.median_lead_minutes,
        }
        for lead in snapshot.lead_channels
    ]
    if since_snapshot_id is not None:
        # Resolve the target once. A concurrent publication must not move it
        # while we load the agent's chosen baseline.
        baseline = (
            snapshot
            if since_snapshot_id == snapshot.snapshot_id
            else await store.get_snapshot(since_snapshot_id)
        )
        payload.update(
            {
                "since_snapshot_id": since_snapshot_id,
                "compared_to": baseline.snapshot_id if baseline else None,
                "comparison_status": "ok" if baseline else "baseline_unavailable",
                "response_mode": "delta" if baseline else "full",
                "baseline_coverage": _status(baseline, now)["coverage"] if baseline else None,
                "baseline_limitations": list(baseline.limitations) if baseline else None,
                "changes": None,
                "agenda_story_ids": [card.story_id for card in snapshot.agenda],
                "upcoming_story_ids": [card.story_id for card in snapshot.upcoming],
            }
        )
        if baseline is not None:
            shared = {card.story_id for card in (*snapshot.agenda, *snapshot.upcoming)} & {
                card.story_id for card in (*baseline.agenda, *baseline.upcoming)
            }
            payload["comparison_limitations"] = (
                ["publication_details_unavailable"]
                if any(sid not in snapshot.stories or sid not in baseline.stories for sid in shared)
                else []
            )
            changes = compare_snapshots(snapshot, baseline)
            payload["changes"] = changes
            changed_ids = {
                change["story_id"]
                for change in (*changes["new_stories"], *changes["updated_stories"])
            }
            payload["stories"] = [
                card for card in payload["stories"] if card["story_id"] in changed_ids
            ]
            payload["upcoming"] = [
                card for card in payload["upcoming"] if card["story_id"] in changed_ids
            ]
            # This ranking is snapshot context, not a change in story evidence.
            payload["lead_channels"] = []
    payload["brief_markdown"] = render_agenda_md(payload)
    return payload


async def story_payload(
    store: AgendaStore, story_id: str, *, snapshot_id: str | None, now: datetime
) -> dict:
    snapshot = await load_snapshot(store, snapshot_id)
    detail = snapshot.stories.get(story_id)
    if detail is None:
        raise AgendaNotFound(f"unknown story {story_id}")
    payload = _status(snapshot, now)
    payload["story"] = _detail_payload(detail)
    payload["brief_markdown"] = render_story_md(payload)
    return payload


async def search_payload(
    store: AgendaStore,
    query: str,
    *,
    snapshot_id: str | None,
    now: datetime,
    limit: int = SEARCH_DEFAULT_LIMIT,
    offset: int = 0,
) -> dict:
    snapshot = await load_snapshot(store, snapshot_id)
    hits, total = search_in_snapshot(snapshot, query, limit=limit, offset=offset)
    payload = _status(snapshot, now)
    payload["query"] = query
    payload["total"] = total
    payload["limit"] = max(1, min(limit, SEARCH_MAX_LIMIT))
    payload["offset"] = max(0, offset)
    payload["hits"] = [
        {
            "story_id": hit.story_id,
            "title": hit.title,
            "matched": list(hit.matched),
        }
        for hit in hits
    ]
    payload["brief_markdown"] = "\n".join(f"- {hit.title} (`{hit.story_id}`)" for hit in hits) + (
        "\n" if hits else "No matching stories.\n"
    )
    return payload


async def health_payload(store: AgendaStore, *, now: datetime, commit: str) -> dict:
    state: CycleState = await store.get_cycle_state()
    snapshot = await store.get_snapshot(None)
    queue_depth = await store.queue_depth()
    queue_stopped = len(await store.queued_ids()) - queue_depth
    last_full_success_at = state.last_full_success_at or state.last_success_at
    if snapshot is None:
        status = "preparing"
    elif state.budget_blocked or state.last_error or is_stale(snapshot.published_at, now):
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "commit": commit,
        "cycle": {
            "phase": state.phase,
            "last_error": _safe_cycle_error(state.last_error),
            "last_success_at": state.last_success_at.isoformat() if state.last_success_at else None,
            "last_collect_at": state.last_collect_at.isoformat() if state.last_collect_at else None,
            "last_partial_at": state.last_partial_at.isoformat() if state.last_partial_at else None,
            "last_full_success_at": (
                last_full_success_at.isoformat() if last_full_success_at else None
            ),
            "queue_depth": queue_depth,
            "queue_stopped": queue_stopped,
        },
        "last_snapshot": None
        if snapshot is None
        else {
            "id": snapshot.snapshot_id,
            "t": snapshot.t.isoformat(),
            "stale": is_stale(snapshot.published_at, now),
            "age_seconds": max(0, int((now - snapshot.published_at).total_seconds())),
        },
        "budget_blocked": state.budget_blocked,
    }


def _safe_cycle_error(error: str) -> str:
    if not error:
        return ""
    if error == "Daily global LLM budget exhausted":
        return error
    if error.isidentifier() and len(error) <= 80:
        return error
    return "analysis_error"
