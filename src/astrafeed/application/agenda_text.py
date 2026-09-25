"""Wording shared by the Markdown and HTML reports: counts, growth, evidence lines."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

_LIMITATION_TEXT = {
    "processing_in_progress": "processing is still running, some posts are not counted yet",
    "evidence_verification_failed": "quote verification did not run, stories are unverified",
    "too_few_comparable_channels": "too few sources to compare with yesterday, no growth",
    "no_new_or_growing_stories": "no new or growing stories",
}
CARD_QUOTES = 3


def channel_count(n: int) -> str:
    return f"{n} source" if n == 1 else f"{n} sources"


def short_time(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%b %d, %H:%M UTC")


def growth_text(card: dict) -> str:
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


def meta_text(card: dict) -> str:
    return " · ".join(
        [*card["entities"][:5], f"story tracked since {short_time(card['first_seen'])}"]
    )


def channel_links(card: dict) -> list[tuple[str, str, str]]:
    """(channel, first post link, note) per channel in spread order; note marks copies."""
    signals = card.get("signals")
    if signals and signals["sources"]:
        result = []
        for index, node in enumerate(signals["sources"]):
            minutes = node["minutes_after_first"]
            note = (
                f"+{duration_text(minutes)}"
                if minutes
                else ("first" if index == 0 else "same minute")
            )
            if node["echo_of"]:
                note = f"copy of {node['echo_of']}, {note}"
            result.append((node["channel"], node["link"], note))
        return result
    seen: dict[str, str] = {}
    for claim in card["claims"]:
        seen.setdefault(claim["channel"], claim["link"])
    return [(name, link, "") for name, link in seen.items()]


def source_group(name: str, link: str) -> str:
    host = (urlsplit(link).hostname or "").lower()
    if host in {"t.me", "telegram.me"}:
        return "Telegram"
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return "X"
    if host in {"reddit.com", "www.reddit.com", "old.reddit.com", "redd.it"} or name.startswith(
        "r/"
    ):
        return "Reddit"
    return "News sites" if host else "Other sources"


def head_start(lead: dict) -> str:
    minutes = lead["median_lead_minutes"]
    return f"median head start {duration_text(minutes)}" if minutes else "tied with another channel"


def duration_text(minutes: int) -> str:
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


def evidence_lines(card: dict) -> list[str]:
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
            f"⏱ First linked source: {first['channel']} at {utc_clock(first['published_at'])} → "
            f"{channel_count(len(sources))} in {duration_text(signals['spread_minutes'])}"
        )
    if signals["figures_conflict"]:
        parts = [
            f"{_usd(f['usd'])} ({channel_count(len(f['channels']))}: {', '.join(f['channels'])})"
            for f in signals["figures"]
        ]
        lines.append("⚠️ Figures differ: " + " vs ".join(parts))
    official_after = signals.get("official_after_minutes")
    if official_after and signals["confirmation"] != "official":
        official_after = None
    if official_after:
        delay = duration_text(official_after)
        lines.append(f"🕰 First post citing an official statement: {delay} after the first post")
    price = signals.get("price")
    if price:
        lines.append(_price_line(price))
        trail = _move_done_line(price)
        if trail:
            lines.append(trail)
    return lines


def _move_done_line(price: dict) -> str:
    """Where each original source stood on the price move, e.g. "@a 20% · @b 90%"."""
    points = [p for p in price.get("at_posts") or [] if p["move_done_pct"] is not None]
    if len(points) < 2:
        return ""
    trail = " · ".join(f"{p['channel']} {p['move_done_pct']}%" for p in points)
    return f"⏳ Share of the move already done when each source posted: {trail}"


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


def utc_clock(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%H:%M UTC")


def count_text(card: dict) -> str:
    text = channel_count(card["current_channels"])
    signals = card.get("signals")
    if signals and signals["echo_channels"]:
        text += (
            f" ({signals['independent_channels']} independent, {signals['echo_channels']} "
            f"{'copy' if signals['echo_channels'] == 1 else 'copies'})"
        )
    return text


def coverage_text(payload: dict) -> str:
    cov = payload["coverage"]
    text = (
        f"{channel_count(cov['channels_ok'])}, {cov['publications_processed']} "
        f"of {cov['publications_total']} posts analyzed"
    )
    if cov["channels_failed"]:
        text += f", {cov['channels_failed']} unavailable"
    if cov.get("channels_incomplete", 0):
        text += f", {cov['channels_incomplete']} incompletely sampled"
    return text


def trust_line(payload: dict) -> str | None:
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
            f"{channel_count(cov['channels_ok'])}, "
            f"{cov.get('publications_processed', 0)}/{cov['publications_total']} posts"
        )
    return " · ".join(parts) if parts else None


def limitation_notes(payload: dict) -> list[str]:
    notes = [_LIMITATION_TEXT.get(code, code) for code in payload["limitations"]]
    return ["snapshot is stale", *notes] if payload["stale"] else notes


def english_text(item: dict, key: str = "quote") -> str:
    """Quote text for the report: the translation when the original is not English."""
    return item.get("translation") or item[key]


def comment_facts(discussion: dict) -> list[tuple[str, dict | None]]:
    """Reader facts paired with the comment that states each one."""
    quotes = discussion["quotes"]
    highlights = discussion.get("highlights", [])
    paired = len(quotes) == len(highlights)
    return [(fact, quotes[k] if paired else None) for k, fact in enumerate(highlights)]


AGENDA_LEAD = (
    "AstraFeed · OKX.AI A2MCP. Stories that appeared or gained sources "
    "over the last 24 hours compared with the previous 24 hours. "
    "Growth counts only sources complete in both windows."
)
EMPTY_AGENDA = "No new or growing stories across comparable sources."
