"""Read published snapshots. HTTP never triggers LLM or collection."""

from __future__ import annotations

import re
from datetime import datetime

from astrafeed.domain.agenda import (
    SEARCH_DEFAULT_LIMIT,
    SEARCH_MAX_LIMIT,
    CycleState,
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
                "link": claim.link,
                "channel": claim.channel_ref,
            }
            for claim in card.claims
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


def render_agenda_md(payload: dict) -> str:
    lines = [
        f"# Повестка ({payload['t']})",
        "",
        f"Снимок `{payload['snapshot_id']}`" + (" · устарел" if payload["stale"] else ""),
    ]
    if payload["limitations"]:
        lines.append("Ограничения: " + ", ".join(payload["limitations"]))
    if not payload["stories"]:
        lines += ["", "Нет новых или растущих сюжетов на сопоставимом наборе каналов."]
        return "\n".join(lines) + "\n"
    for card in payload["stories"]:
        growth = card["growth"]
        growth_s = f"{growth:+d}" if isinstance(growth, int) else "н/д"
        lines += [
            "",
            f"## {card['title']}",
            f"Каналы: {card['current_channels']} (изменение {growth_s})",
            card["explanation"],
        ]
        for claim in card["claims"]:
            lines.append(f"- «{claim['quote']}» — {claim['link']}")
    return "\n".join(lines) + "\n"


def render_story_md(payload: dict) -> str:
    card = payload["story"]
    lines = [f"# {card['title']}", "", card["explanation"], ""]
    for claim in card["claims"]:
        lines.append(f"- «{claim['quote']}» — {claim['link']}")
    return "\n".join(lines) + "\n"


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
    for story_id, docs in docs_by_story.items():
        title = next((doc.text for doc in docs if doc.kind == "title"), story_id)
        matches = []
        found: set[str] = set()
        score = 0.0
        for doc in docs:
            terms = {_search_term(token) for token in re.findall(r"[\w]+", doc.text.casefold())}
            overlap = terms & query_terms
            if overlap:
                found.update(overlap)
                weight = {"title": 10.0, "entity": 4.0, "alias": 3.0,
                          "claim": 2.0, "publication": 1.0}[doc.kind]
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
        scored.append(SearchHit(story_id, title, tuple(matches), score))
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


async def agenda_payload(store: AgendaStore, *, snapshot_id: str | None, now: datetime) -> dict:
    snapshot = await load_snapshot(store, snapshot_id)
    payload = _status(snapshot, now)
    payload["stories"] = [_card_payload(card) for card in snapshot.agenda]
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
        "\n" if hits else "Ничего не найдено.\n"
    )
    return payload


async def health_payload(store: AgendaStore, *, now: datetime, commit: str) -> dict:
    state: CycleState = await store.get_cycle_state()
    snapshot = await store.get_snapshot(None)
    queue_depth = await store.queue_depth()
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
                state.last_full_success_at.isoformat() if state.last_full_success_at else None
            ),
            "queue_depth": queue_depth,
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
