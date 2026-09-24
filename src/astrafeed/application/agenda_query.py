"""Read published snapshots. HTTP never triggers LLM or collection."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from urllib.parse import quote

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


_LIMITATION_TEXT = {
    "processing_in_progress": "обработка ещё идёт, часть постов не учтена",
    "evidence_verification_failed": "проверка цитат не выполнилась, сюжеты не проверены",
    "too_few_comparable_channels": "мало каналов для сравнения со вчера, рост не считаем",
    "no_new_or_growing_stories": "новых или растущих сюжетов нет",
}
_CARD_QUOTES = 3


def _channels(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} канал"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} канала"
    return f"{n} каналов"


def _when(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d.%m %H:%M UTC")


def _growth_text(card: dict) -> str:
    growth = card["growth"]
    if not isinstance(growth, int):
        return "рост н/д"
    if growth > 0:
        return f"↑ +{growth} за сутки"
    return f"↓ {growth} за сутки" if growth < 0 else "без изменений за сутки"


def _meta_text(card: dict) -> str:
    return " · ".join([*card["entities"][:5], f"впервые {_when(card['first_seen'])}"])


def _channel_links(card: dict) -> list[tuple[str, str]]:
    """One (channel, post link) pair per channel, in claim order."""
    seen: dict[str, str] = {}
    for claim in card["claims"]:
        seen.setdefault(claim["channel"], claim["link"])
    return list(seen.items())


def _coverage_text(payload: dict) -> str:
    cov = payload["coverage"]
    text = (
        f"{_channels(cov['channels_ok'])}, разобрано {cov['publications_processed']} "
        f"из {cov['publications_total']} постов"
    )
    if cov["channels_failed"]:
        text += f", недоступно каналов: {cov['channels_failed']}"
    return text


def _limitation_notes(payload: dict) -> list[str]:
    notes = [_LIMITATION_TEXT.get(code, code) for code in payload["limitations"]]
    return ["снимок устарел", *notes] if payload["stale"] else notes


def _md_quote(item: dict) -> list[str]:
    return ["", f"> «{item['quote']}» — [{item['channel']}]({item['link']})"]


def _md_card_head(card: dict, heading: str) -> list[str]:
    lines = [
        heading,
        "",
        f"**{_channels(card['current_channels'])}** · {_growth_text(card)}  ",
        _meta_text(card),
        "",
        card["explanation"],
    ]
    channels = _channel_links(card)
    if channels:
        lines += ["", "Пишут: " + " · ".join(f"[{name}]({link})" for name, link in channels)]
    return lines


def render_agenda_md(payload: dict) -> str:
    lines = [
        f"# Повестка крипто-Telegram · {_when(payload['t'])}",
        "",
        "Сюжеты, которые за последние 24 часа появились или набрали каналы "
        "по сравнению с предыдущими сутками.",
        "",
        f"Охват: {_coverage_text(payload)}. Снимок `{payload['snapshot_id']}`.",
    ]
    notes = _limitation_notes(payload)
    if notes:
        lines += ["", "⚠️ " + "; ".join(notes) + "."]
    if not payload["stories"]:
        lines += ["", "Нет новых или растущих сюжетов на сопоставимом наборе каналов."]
        return "\n".join(lines) + "\n"
    for index, card in enumerate(payload["stories"], 1):
        lines += ["", "---", ""]
        lines += _md_card_head(card, f"## {index}. {card['title']}")
        for claim in card["claims"][:_CARD_QUOTES]:
            lines += _md_quote(claim)
    return "\n".join(lines) + "\n"


def render_story_md(payload: dict) -> str:
    card = payload["story"]
    lines = _md_card_head(card, f"# {card['title']}")
    if card["claims"]:
        lines += ["", "## Что пишут"]
        for claim in card["claims"]:
            lines += _md_quote(claim)
    if card.get("positions"):
        lines += ["", "## Мнения авторов"]
        for position in card["positions"]:
            lines += _md_quote(position)
    if card.get("publications"):
        lines += ["", "## Посты"]
        lines += [
            f"- {_when(pub['published_at'])} [{pub['channel']}]({pub['link']})"
            for pub in card["publications"]
        ]
    lines += ["", f"Снимок `{payload['snapshot_id']}` · {_coverage_text(payload)}."]
    return "\n".join(lines) + "\n"


_PAGE_CSS = """
:root{--bg:#f7f6f2;--card:#fff;--ink:#1d1d1b;--muted:#6b6a64;--line:#e4e2da;--accent:#0b6bcb;
--up:#1a7f37;--warn:#fff4d6}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--ink:#ecebe6;
--muted:#a3a29b;--line:#34332f;--accent:#6cb2ff;--up:#56d17a;--warn:#3a3217}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.6rem;margin:0 0 4px}.lead,.meta,footer{color:var(--muted)}
.lead{margin:0 0 12px}.meta{font-size:.9rem}
.note{background:var(--warn);border-radius:8px;padding:8px 12px;margin:12px 0}
article{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px 18px;margin:16px 0}
article h2{font-size:1.2rem;margin:0 0 6px}h2 a{color:inherit;text-decoration:none}
h2 a:hover{text-decoration:underline}
.stat{font-weight:600}.up{color:var(--up)}a{color:var(--accent)}
blockquote{margin:10px 0;padding:2px 0 2px 12px;border-left:3px solid var(--line)}
blockquote cite{display:block;font-style:normal;color:var(--muted);font-size:.9rem}
ul{padding-left:20px}footer{font-size:.85rem;margin-top:24px}
"""


def _url(link: str) -> str:
    return escape(link) if link.startswith(("https://", "http://")) else "#"


def _html_quote(item: dict) -> str:
    return (
        f"<blockquote>«{escape(item['quote'])}»<cite>— "
        f'<a href="{_url(item["link"])}">{escape(item["channel"])}</a></cite></blockquote>'
    )


def _html_card_head(card: dict, title_html: str) -> str:
    growth_class = ' class="up"' if isinstance(card["growth"], int) and card["growth"] > 0 else ""
    parts = [
        title_html,
        f'<p><span class="stat">{_channels(card["current_channels"])}</span> · '
        f"<span{growth_class}>{escape(_growth_text(card))}</span><br>"
        f'<span class="meta">{escape(_meta_text(card))}</span></p>',
        f"<p>{escape(card['explanation'])}</p>",
    ]
    channels = _channel_links(card)
    if channels:
        links = " · ".join(f'<a href="{_url(link)}">{escape(name)}</a>' for name, link in channels)
        parts.append(f"<p>Пишут: {links}</p>")
    return "".join(parts)


def _html_page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_PAGE_CSS}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


def _html_status(payload: dict) -> str:
    notes = _limitation_notes(payload)
    note = f'<p class="note">⚠️ {escape("; ".join(notes))}.</p>' if notes else ""
    return f'<p class="meta">Охват: {escape(_coverage_text(payload))}.</p>{note}'


def render_agenda_html(payload: dict) -> str:
    snapshot = quote(payload["snapshot_id"])
    body = [
        f"<h1>Повестка крипто-Telegram · {escape(_when(payload['t']))}</h1>",
        '<p class="lead">Сюжеты, которые за последние 24 часа появились или набрали '
        "каналы по сравнению с предыдущими сутками.</p>",
        _html_status(payload),
    ]
    if not payload["stories"]:
        body.append("<p>Нет новых или растущих сюжетов на сопоставимом наборе каналов.</p>")
    for index, card in enumerate(payload["stories"], 1):
        href = f"/stories/{quote(card['story_id'])}?format=html&amp;snapshot_id={snapshot}"
        title = f'<h2><a href="{href}">{index}. {escape(card["title"])}</a></h2>'
        quotes = "".join(_html_quote(claim) for claim in card["claims"][:_CARD_QUOTES])
        body.append(f"<article>{_html_card_head(card, title)}{quotes}</article>")
    body.append(
        f"<footer>Снимок {escape(payload['snapshot_id'])} · "
        f'<a href="/agenda?format=md&amp;snapshot_id={snapshot}">Markdown</a> · '
        f'<a href="/agenda?snapshot_id={snapshot}">JSON</a></footer>'
    )
    return _html_page("Повестка крипто-Telegram", "".join(body))


def render_story_html(payload: dict) -> str:
    card = payload["story"]
    snapshot = quote(payload["snapshot_id"])
    body = [
        f'<p class="meta"><a href="/agenda?format=html&amp;snapshot_id={snapshot}">'
        "← Повестка</a></p>",
        f"<article>{_html_card_head(card, f'<h1>{escape(card["title"])}</h1>')}</article>",
    ]
    if card["claims"]:
        body.append("<h2>Что пишут</h2>" + "".join(_html_quote(c) for c in card["claims"]))
    if card.get("positions"):
        body.append("<h2>Мнения авторов</h2>" + "".join(_html_quote(p) for p in card["positions"]))
    if card.get("publications"):
        items = "".join(
            f"<li>{escape(_when(pub['published_at']))} "
            f'<a href="{_url(pub["link"])}">{escape(pub["channel"])}</a></li>'
            for pub in card["publications"]
        )
        body.append(f"<h2>Посты</h2><ul>{items}</ul>")
    body.append(f"<footer>{_html_status(payload)}Снимок {escape(payload['snapshot_id'])}</footer>")
    return _html_page(card["title"], "".join(body))


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
                (state.last_full_success_at or state.last_success_at).isoformat()
                if state.last_full_success_at or state.last_success_at
                else None
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
