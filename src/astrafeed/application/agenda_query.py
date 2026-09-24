"""Read published snapshots. HTTP never triggers LLM or collection."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from urllib.parse import quote, urlsplit

from astrafeed.application.agenda_changes import compare_snapshots, comparison_lines
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


_LIMITATION_TEXT = {
    "processing_in_progress": "processing is still running, some posts are not counted yet",
    "evidence_verification_failed": "quote verification did not run, stories are unverified",
    "too_few_comparable_channels": "too few sources to compare with yesterday, no growth",
    "no_new_or_growing_stories": "no new or growing stories",
}
_CARD_QUOTES = 3


def _channels(n: int) -> str:
    return f"{n} source" if n == 1 else f"{n} sources"


def _when(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%b %d, %H:%M UTC")


def _growth_text(card: dict) -> str:
    growth = card["growth"]
    if not isinstance(growth, int):
        return "growth n/a"
    if growth > 0:
        text = f"↑ +{growth} in 24h"
    elif growth < 0:
        text = f"↓ {growth} in 24h"
    else:
        text = "no change in 24h"
    current = card.get("current_channels")
    previous = card.get("previous_channels") or 0
    if isinstance(current, int) and current != previous + growth:
        text += f" on comparable sources ({current} observed)"
    return text


def _meta_text(card: dict) -> str:
    return " · ".join([*card["entities"][:5], f"story tracked since {_when(card['first_seen'])}"])


def _channel_links(card: dict) -> list[tuple[str, str, str]]:
    """(channel, first post link, note) per channel in spread order; note marks copies."""
    signals = card.get("signals")
    if signals and signals["sources"]:
        result = []
        for index, node in enumerate(signals["sources"]):
            minutes = node["minutes_after_first"]
            note = (
                f"+{_duration(minutes)}" if minutes else ("first" if index == 0 else "same minute")
            )
            if node["echo_of"]:
                note = f"copy of {node['echo_of']}, {note}"
            result.append((node["channel"], node["link"], note))
        return result
    seen: dict[str, str] = {}
    for claim in card["claims"]:
        seen.setdefault(claim["channel"], claim["link"])
    return [(name, link, "") for name, link in seen.items()]


def _source_group(name: str, link: str) -> str:
    host = (urlsplit(link).hostname or "").lower()
    if host in {"t.me", "telegram.me"}:
        return "Telegram"
    if host in {"reddit.com", "www.reddit.com", "old.reddit.com", "redd.it"} or name.startswith(
        "r/"
    ):
        return "Reddit"
    return "News sites" if host else "Other sources"


def _head_start(lead: dict) -> str:
    minutes = lead["median_lead_minutes"]
    return f"median head start {_duration(minutes)}" if minutes else "tied with another channel"


def _duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h {rest:02d}m" if rest else f"{hours}h"


_CONFIRMATION = {
    "official": "✅ cites an official statement",
    "attributed": "🟡 attributed",
    "rumor": "🔴 unconfirmed / rumor",
}
_PRICE_VERDICT = {
    "priced_in": "price already moved before the first Telegram post",
    "telegram_ahead": "Telegram posted before a material price move",
    "both_moved": "price moved both before and after the first post",
    "quiet": "no material price move around the first post",
}


def _usd(value: float) -> str:
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= size:
            return f"${value / size:.3g}{suffix}"
    return f"${value:,.0f}"


def _signal_lines(card: dict) -> list[str]:
    """Evidence lines computed by code: independence, sourcing, spread, figures, price."""
    signals = card.get("signals")
    if not signals:
        return []
    lines: list[str] = []
    sourcing = _CONFIRMATION.get(signals["confirmation"], "")
    if sourcing and signals["confirmation"] == "attributed" and signals["attributed_to"]:
        sourcing += ": " + ", ".join(signals["attributed_to"])
    if sourcing:
        lines.append(f"Sourcing: {sourcing}")
    sources = signals["sources"]
    if len(sources) >= 2 and signals["spread_minutes"] is not None:
        first = sources[0]
        lines.append(
            f"⏱ First linked source: {first['channel']} at {_clock(first['published_at'])} → "
            f"{_channels(len(sources))} in {_duration(signals['spread_minutes'])}"
        )
    if signals["figures_conflict"]:
        parts = [
            f"{_usd(f['usd'])} ({_channels(len(f['channels']))}: {', '.join(f['channels'])})"
            for f in signals["figures"]
        ]
        lines.append("⚠️ Figures differ: " + " vs ".join(parts))
    price = signals.get("price")
    if price:
        lines.append(_price_line(price))
    return lines


def _price_line(price: dict) -> str:
    arrow = "📈" if price["change_pct"] >= 0 else "📉"
    symbol = price["inst_id"].split("-")[0]
    before = price.get("change_pct_before")
    hour_before = price.get("price_hour_before")
    verdict = _PRICE_VERDICT.get(price.get("verdict") or "", "")
    note = f"{verdict} (OKX spot; not causal)" if verdict else "OKX spot; not causal"
    if before is not None and hour_before is not None:
        return (
            f"{arrow} {symbol} {before:+.2f}% in the hour before first post, "
            f"{price['change_pct']:+.2f}% after "
            f"({hour_before:g} → {price['price_then']:g} → {price['price_now']:g} USDT). {note}"
        )
    return (
        f"{arrow} {symbol} {price['change_pct']:+.2f}% since first post "
        f"({price['price_then']:g} → {price['price_now']:g} USDT, {note})"
    )


def _clock(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%H:%M UTC")


def _count_text(card: dict) -> str:
    text = _channels(card["current_channels"])
    signals = card.get("signals")
    if signals and signals["echo_channels"]:
        text += (
            f" ({signals['independent_channels']} independent, {signals['echo_channels']} "
            f"{'copy' if signals['echo_channels'] == 1 else 'copies'})"
        )
    return text


def _coverage_text(payload: dict) -> str:
    cov = payload["coverage"]
    text = (
        f"{_channels(cov['channels_ok'])}, {cov['publications_processed']} "
        f"of {cov['publications_total']} posts analyzed"
    )
    if cov["channels_failed"]:
        text += f", {cov['channels_failed']} unavailable"
    return text


def _trust_line(payload: dict) -> str | None:
    """Measured snapshot facts: displayed quotes, cycle time, and coverage."""
    parts: list[str] = []
    quotes = sum(len(card.get("claims") or []) for card in payload.get("stories") or [])
    if quotes:
        noun = "quote" if quotes == 1 else "quotes"
        parts.append(f"{quotes} displayed {noun} passed the span check")
    collected = payload.get("collected_at")
    published = payload.get("published_at") or payload.get("analyzed_at")
    if collected and published:
        seconds = int(
            (datetime.fromisoformat(published) - datetime.fromisoformat(collected)).total_seconds()
        )
        if seconds >= 0:
            parts.append(f"{seconds}s collect→publish")
    cov = payload.get("coverage") or {}
    if cov.get("channels_ok") is not None and cov.get("publications_total") is not None:
        parts.append(
            f"{_channels(cov['channels_ok'])}, "
            f"{cov.get('publications_processed', 0)}/{cov['publications_total']} posts"
        )
    return " · ".join(parts) if parts else None


def _limitation_notes(payload: dict) -> list[str]:
    notes = [_LIMITATION_TEXT.get(code, code) for code in payload["limitations"]]
    return ["snapshot is stale", *notes] if payload["stale"] else notes


def _english(item: dict, key: str = "quote") -> str:
    """Quote text for the report: the translation when the original is not English."""
    return item.get("translation") or item[key]


def _md_quote(item: dict) -> list[str]:
    return ["", f"> “{_english(item)}” — [{item['channel']}]({item['link']})"]


def _md_card_head(card: dict, heading: str) -> list[str]:
    lines = [
        heading,
        "",
        f"**{_count_text(card)}** · {_growth_text(card)}  ",
        _meta_text(card),
        "",
        card["explanation"],
    ]
    signal_lines = _signal_lines(card)
    if signal_lines:
        lines += [""] + [f"{line}  " for line in signal_lines]
    caveat = (card.get("signals") or {}).get("caveat_drop")
    if caveat:
        lines += [
            "",
            f"⚠️ **Qualifier dropped in later wording** (+{_duration(caveat['minutes_later'])}):",
            f"- [{caveat['before_channel']}]({caveat['before_link']}): “{caveat['before_quote']}”",
            f"- [{caveat['after_channel']}]({caveat['after_link']}): “{caveat['after_quote']}”",
        ]
    channels = _channel_links(card)
    if channels:
        lines += [
            "",
            "Covered by: "
            + " · ".join(
                f"[{name}]({link})" + (f" ({note})" if note else "")
                for name, link, note in channels
            ),
        ]
    return lines


def _comment_facts(discussion: dict) -> list[tuple[str, dict | None]]:
    """Reader facts paired with the comment that states each one."""
    quotes = discussion["quotes"]
    highlights = discussion.get("highlights", [])
    paired = len(quotes) == len(highlights)
    return [(fact, quotes[k] if paired else None) for k, fact in enumerate(highlights)]


def _md_discussion(card: dict, *, full: bool) -> list[str]:
    discussion = card.get("discussion")
    if not discussion:
        return []
    facts = _comment_facts(discussion)
    if not facts and not discussion["points"]:
        return []
    lines = [
        "",
        f"💬 **From reader comments** ({discussion['comment_count']} comments, unverified):",
    ]
    # Snapshots published before facts-only comments carry opinion points.
    lines += [f"- {point}" for point in discussion["points"]]
    for fact, comment in facts:
        source = f" — [discussion in {comment['channel']}]({comment['link']})" if comment else ""
        lines.append(f"- {fact}{source}")
        if full and comment:
            lines.append(f"  > “{_english(comment, 'text')}”")
    return lines


_LEAD = (
    "AstraFeed · OKX.AI A2MCP. Stories that appeared or gained sources "
    "over the last 24 hours compared with the previous 24 hours. "
    "Growth counts only sources complete in both windows."
)
_EMPTY = "No new or growing stories across comparable sources."


def render_agenda_md(payload: dict) -> str:
    delta = payload.get("response_mode") == "delta"
    lines = [
        f"# Crypto agenda · {_when(payload['t'])}",
        "",
        "New and updated cards relative to the requested snapshot." if delta else _LEAD,
        "",
        f"Coverage: {_coverage_text(payload)}. Snapshot `{payload['snapshot_id']}`.",
    ]
    notes = _limitation_notes(payload)
    if notes:
        lines += ["", "⚠️ " + "; ".join(notes) + "."]
    lines += ["", *comparison_lines(payload)]
    if not payload["stories"]:
        if not delta:
            lines += ["", _EMPTY]
        lines += _md_extras(payload)
        lines += _md_footer(payload)
        return "\n".join(lines) + "\n"
    for index, card in enumerate(payload["stories"], 1):
        lines += ["", "---", ""]
        lines += _md_card_head(card, f"## {index}. {card['title']}")
        for claim in card["claims"][:_CARD_QUOTES]:
            lines += _md_quote(claim)
        lines += _md_discussion(card, full=False)
    lines += _md_extras(payload)
    lines += _md_footer(payload)
    return "\n".join(lines) + "\n"


def _md_footer(payload: dict) -> list[str]:
    lines = [
        "",
        "---",
        "",
        "_Quotes from non-English posts and comments are machine-translated. "
        "Copies are posts that repeat an earlier source's text near-verbatim; "
        "they add reach, not confirmation. Prices are context, not cause._",
    ]
    trust = _trust_line(payload)
    if trust:
        lines += ["", trust]
    return lines


def _md_extras(payload: dict) -> list[str]:
    lines: list[str] = []
    leads = payload.get("lead_channels") or []
    if leads:
        lines += ["", "---", "", "## ⚡ First to report"]
        lines += [
            f"- **{lead['channel']}** — first on {lead['stories_first']} "
            f"{'story' if lead['stories_first'] == 1 else 'stories'}, {_head_start(lead)}"
            for lead in leads
        ]
    upcoming = payload.get("upcoming") or []
    if upcoming:
        lines += ["", "## 📅 On the calendar"]
        lines += [f"- {card['title']} ({_channels(card['current_channels'])})" for card in upcoming]
    return lines


def render_story_md(payload: dict) -> str:
    card = payload["story"]
    lines = _md_card_head(card, f"# {card['title']}")
    if card["claims"]:
        lines += ["", "## What sources say"]
        for claim in card["claims"]:
            lines += _md_quote(claim)
    lines += _md_discussion(card, full=True)
    if card.get("positions"):
        lines += ["", "## Author opinions"]
        for position in card["positions"]:
            lines += _md_quote(position)
    if card.get("publications"):
        lines += ["", "## Posts"]
        lines += [
            f"- {_when(pub['published_at'])} [{pub['channel']}]({pub['link']})"
            for pub in card["publications"]
        ]
    lines += ["", f"Snapshot `{payload['snapshot_id']}` · {_coverage_text(payload)}."]
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
.talk{border-top:1px dashed var(--line);margin-top:12px;padding-top:8px}
.talk ul{margin:4px 0}
details{color:var(--muted);font-size:.85rem}summary{cursor:pointer}
.sig{font-size:.92rem;margin:8px 0;padding:0;list-style:none}.sig li{margin:2px 0}
.conflict{background:var(--warn);border-radius:6px;padding:2px 6px}
.tl{position:relative;height:30px;margin:10px 4px 2px;border-top:2px solid var(--line)}
.tl a{position:absolute;top:-7px;width:12px;height:12px;margin-left:-6px;border-radius:50%;
background:var(--accent)}.tl a.echo{background:var(--card);border:2px solid var(--muted)}
.tl span{position:absolute;top:8px;font-size:.75rem;color:var(--muted);white-space:nowrap}
.src .echo{color:var(--muted)}
.source-group{display:flex;gap:10px;margin:4px 0}.source-group>span{min-width:85px;
color:var(--muted);font-weight:600}.source-group>div{flex:1}
"""


def _url(link: str) -> str:
    return escape(link) if link.startswith(("https://", "http://")) else "#"


def _html_original(item: dict, key: str = "quote") -> str:
    if not item.get("translation"):
        return ""
    return f"<details><summary>original</summary>{escape(item[key])}</details>"


def _html_quote(item: dict) -> str:
    return (
        f"<blockquote>“{escape(_english(item))}”<cite>— "
        f'<a href="{_url(item["link"])}">{escape(item["channel"])}</a></cite>'
        f"{_html_original(item)}</blockquote>"
    )


def _html_timeline(card: dict) -> str:
    """Dots along the spread window: filled for originals, hollow for copies."""
    signals = card.get("signals")
    if not signals or len(signals["sources"]) < 2 or not signals["spread_minutes"]:
        return ""
    span = signals["spread_minutes"]
    dots = "".join(
        f'<a class="{"echo" if node["echo_of"] else ""}" '
        f'style="left:{node["minutes_after_first"] / span * 100:.1f}%" '
        f'href="{_url(node["link"])}" title="{escape(node["channel"])} '
        f'{escape(_clock(node["published_at"]))}"></a>'
        for node in signals["sources"]
    )
    first = signals["sources"][0]
    labels = (
        f'<span style="left:0">{escape(_clock(first["published_at"]))}</span>'
        f'<span style="right:0">+{escape(_duration(span))}</span>'
    )
    return f'<div class="tl" aria-label="spread timeline">{dots}{labels}</div>'


def _html_card_head(card: dict, title_html: str) -> str:
    growth_class = ' class="up"' if isinstance(card["growth"], int) and card["growth"] > 0 else ""
    parts = [
        title_html,
        f'<p><span class="stat">{escape(_count_text(card))}</span> · '
        f"<span{growth_class}>{escape(_growth_text(card))}</span><br>"
        f'<span class="meta">{escape(_meta_text(card))}</span></p>',
        f"<p>{escape(card['explanation'])}</p>",
    ]
    signal_lines = _signal_lines(card)
    if signal_lines:
        items = "".join(
            f"<li{' class=conflict' if line.startswith('⚠️') else ''}>{escape(line)}</li>"
            for line in signal_lines
        )
        parts.append(f'<ul class="sig">{items}</ul>')
    caveat = (card.get("signals") or {}).get("caveat_drop")
    if caveat:
        parts.append(
            '<div class="talk"><p><b>⚠️ Qualifier dropped in later wording</b> '
            f"(+{escape(_duration(caveat['minutes_later']))})</p>"
            f"<blockquote>“{escape(caveat['before_quote'])}” <cite>— "
            f'<a href="{_url(caveat["before_link"])}">{escape(caveat["before_channel"])}</a>'
            "</cite></blockquote>"
            f"<blockquote>“{escape(caveat['after_quote'])}” <cite>— "
            f'<a href="{_url(caveat["after_link"])}">{escape(caveat["after_channel"])}</a>'
            "</cite></blockquote></div>"
        )
    parts.append(_html_timeline(card))
    sources = _channel_links(card)
    if sources:
        groups: dict[str, list[str]] = {}
        for name, link, note in sources:
            item = f'<a href="{_url(link)}">{escape(name)}</a>'
            if note:
                item += (
                    f' <span class="{"echo" if "copy" in note else "meta"}">({escape(note)})</span>'
                )
            groups.setdefault(_source_group(name, link), []).append(item)
        sections = "".join(
            f'<div class="source-group"><span>{label}</span>'
            f"<div>{' · '.join(groups[label])}</div></div>"
            for label in ("Telegram", "Reddit", "News sites", "Other sources")
            if label in groups
        )
        parts.append(f'<div class="src"><b>Sources</b>{sections}</div>')
    return "".join(parts)


def _html_discussion(card: dict, *, full: bool) -> str:
    discussion = card.get("discussion")
    if not discussion:
        return ""
    facts = _comment_facts(discussion)
    if not facts and not discussion["points"]:
        return ""
    items = "".join(f"<li>{escape(point)}</li>" for point in discussion["points"])
    for fact, comment in facts:
        source = quote_html = ""
        if comment:
            source = (
                f' — <a href="{_url(comment["link"])}">'
                f"comments under {escape(comment['channel'])} post</a>"
            )
            if full:
                quote_html = (
                    f"<blockquote>“{escape(_english(comment, 'text'))}”"
                    f"{_html_original(comment, 'text')}</blockquote>"
                )
        items += f"<li>{escape(fact)}{source}{quote_html}</li>"
    return (
        f'<div class="talk"><p><b>💬 From reader comments</b> '
        f"({discussion['comment_count']} comments, unverified)</p><ul>{items}</ul></div>"
    )


def _html_page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="description" content="Live crypto agenda with source links.">'
        f'<meta property="og:title" content="{escape(title)}">'
        '<meta property="og:description" content="Crypto stories with source quotes and links.">'
        f"<title>{escape(title)}</title><style>{_PAGE_CSS}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


def _html_status(payload: dict) -> str:
    notes = _limitation_notes(payload)
    note = f'<p class="note">⚠️ {escape("; ".join(notes))}.</p>' if notes else ""
    published = payload.get("published_at")
    snapshot_time = (
        f"Last published snapshot: {_when(published)}. " if published and payload["stale"] else ""
    )
    excluded = "Newer collection is not included in these counts. " if payload["stale"] else ""
    return (
        f'<p class="meta">Coverage in this snapshot: {escape(_coverage_text(payload))}. '
        f"{escape(snapshot_time + excluded)}</p>{note}"
    )


def render_agenda_html(payload: dict) -> str:
    snapshot = quote(payload["snapshot_id"])
    delta = payload.get("response_mode") == "delta"
    lead = "New and updated cards relative to the requested snapshot." if delta else _LEAD
    body = [
        f"<h1>AstraFeed · Crypto agenda · {escape(_when(payload['t']))}</h1>",
        f'<p class="lead">{lead} Same snapshot: <code>POST /a2mcp/astrafeed</code>.</p>',
        _html_status(payload),
    ]
    body.extend(f'<p class="note">{escape(line)}</p>' for line in comparison_lines(payload))
    if not payload["stories"] and not delta:
        body.append(f"<p>{_EMPTY}</p>")
    for index, card in enumerate(payload["stories"], 1):
        href = f"/stories/{quote(card['story_id'])}?format=html&amp;snapshot_id={snapshot}"
        title = f'<h2><a href="{href}">{index}. {escape(card["title"])}</a></h2>'
        quotes = "".join(_html_quote(claim) for claim in card["claims"][:_CARD_QUOTES])
        talk = _html_discussion(card, full=False)
        body.append(f"<article>{_html_card_head(card, title)}{quotes}{talk}</article>")
    leads = payload.get("lead_channels") or []
    if leads:
        items = "".join(
            f"<li><b>{escape(lead['channel'])}</b> — first on {lead['stories_first']} "
            f"{'story' if lead['stories_first'] == 1 else 'stories'}, "
            f"{escape(_head_start(lead))}</li>"
            for lead in leads
        )
        body.append(f"<h2>⚡ First to report</h2><ul>{items}</ul>")
    upcoming = payload.get("upcoming") or []
    if upcoming:
        items = "".join(
            f"<li>{escape(card['title'])} ({_channels(card['current_channels'])})</li>"
            for card in upcoming
        )
        body.append(f"<h2>📅 On the calendar</h2><ul>{items}</ul>")
    baseline_query = (
        f"&amp;since_snapshot_id={quote(payload['since_snapshot_id'], safe='')}"
        if "since_snapshot_id" in payload
        else ""
    )
    trust = _trust_line(payload)
    trust_html = f"<br>{escape(trust)}" if trust else ""
    body.append(
        "<footer>Copies repeat an earlier source's text near-verbatim: reach, not confirmation. "
        "Prices are OKX spot context, not cause. "
        "Quotes from non-English posts and comments are machine-translated. "
        f"Snapshot {escape(payload['snapshot_id'])} · "
        f'<a href="/agenda?format=md&amp;snapshot_id={snapshot}{baseline_query}">Markdown</a> · '
        f'<a href="/agenda?snapshot_id={snapshot}{baseline_query}">JSON</a>'
        f"{trust_html}</footer>"
    )
    return _html_page("AstraFeed · Crypto agenda", "".join(body))


def render_story_html(payload: dict) -> str:
    card = payload["story"]
    snapshot = quote(payload["snapshot_id"])
    body = [
        f'<p class="meta"><a href="/agenda?format=html&amp;snapshot_id={snapshot}">'
        "← Agenda</a></p>",
        f"<article>{_html_card_head(card, f'<h1>{escape(card["title"])}</h1>')}</article>",
    ]
    if card["claims"]:
        body.append("<h2>What sources say</h2>" + "".join(_html_quote(c) for c in card["claims"]))
    body.append(_html_discussion(card, full=True))
    if card.get("positions"):
        body.append("<h2>Author opinions</h2>" + "".join(_html_quote(p) for p in card["positions"]))
    if card.get("publications"):
        items = "".join(
            f"<li>{escape(_when(pub['published_at']))} "
            f'<a href="{_url(pub["link"])}">{escape(pub["channel"])}</a></li>'
            for pub in card["publications"]
        )
        body.append(f"<h2>Posts</h2><ul>{items}</ul>")
    body.append(
        f"<footer>{_html_status(payload)}Snapshot {escape(payload['snapshot_id'])}</footer>"
    )
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
