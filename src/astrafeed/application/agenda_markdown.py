"""Markdown agenda and story reports rendered from a JSON payload."""

from __future__ import annotations

from urllib.parse import quote, urlsplit

from astrafeed.application.agenda_changes import comparison_lines
from astrafeed.application.agenda_text import (
    AGENDA_LEAD,
    CARD_QUOTES,
    EMPTY_AGENDA,
    channel_count,
    channel_links,
    comment_facts,
    count_text,
    coverage_text,
    duration_text,
    english_text,
    evidence_lines,
    growth_text,
    head_start,
    limitation_notes,
    meta_text,
    short_time,
    trust_line,
)


def _md_text(value: object) -> str:
    """Escape untrusted source text before placing it in Markdown prose."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    for char in "\\`*_{}[]()#+-.!|<>":
        text = text.replace(char, "\\" + char)
    return text


def _md_url(value: object) -> str:
    url = str(value)
    try:
        if urlsplit(url).scheme.lower() not in {"http", "https"}:
            return "#"
    except ValueError:
        return "#"
    return quote(url, safe=":/?#@!$&'*+,;=%")


def _md_quote(item: dict) -> list[str]:
    channel = _md_text(item["channel"])
    url = _md_url(item["link"])
    return [
        "",
        f"> “{_md_text(english_text(item))}” — [{channel}](<{url}>)",
    ]


def _md_card_head(card: dict, heading: str) -> list[str]:
    lines = [
        heading,
        "",
        f"**{count_text(card)}** · {growth_text(card)}  ",
        _md_text(meta_text(card)),
        "",
        _md_text(card["explanation"]),
    ]
    signal_lines = evidence_lines(card)
    if signal_lines:
        lines += [""] + [f"{_md_text(line)}  " for line in signal_lines]
    caveat = (card.get("signals") or {}).get("caveat_drop")
    if caveat:
        lines += [
            "",
            "⚠️ **Qualifier dropped in later wording** "
            f"(+{duration_text(caveat['minutes_later'])}):",
            (
                f"- [{_md_text(caveat['before_channel'])}]"
                f"(<{_md_url(caveat['before_link'])}>): “{_md_text(caveat['before_quote'])}”"
            ),
            (
                f"- [{_md_text(caveat['after_channel'])}]"
                f"(<{_md_url(caveat['after_link'])}>): “{_md_text(caveat['after_quote'])}”"
            ),
        ]
    channels = channel_links(card)
    if channels:
        lines += [
            "",
            "Covered by: "
            + " · ".join(
                f"[{_md_text(name)}](<{_md_url(link)}>)" + (f" ({_md_text(note)})" if note else "")
                for name, link, note in channels
            ),
        ]
    return lines


def _md_discussion(card: dict, *, full: bool) -> list[str]:
    discussion = card.get("discussion")
    if not discussion:
        return []
    facts = comment_facts(discussion)
    if not facts and not discussion["points"]:
        return []
    lines = [
        "",
        f"💬 **From reader comments** ({discussion['comment_count']} comments, unverified):",
    ]
    # Snapshots published before facts-only comments carry opinion points.
    lines += [f"- {_md_text(point)}" for point in discussion["points"]]
    for fact, comment in facts:
        source = (
            f" — [comments under {_md_text(comment['channel'])} post](<{_md_url(comment['link'])}>)"
            if comment
            else ""
        )
        lines.append(f"- {_md_text(fact)}{source}")
        if full and comment:
            lines.append(f"  > “{_md_text(english_text(comment, 'text'))}”")
    return lines


def render_agenda_md(payload: dict) -> str:
    delta = payload.get("response_mode") == "delta"
    lines = [
        f"# Crypto agenda · {short_time(payload['t'])}",
        "",
        "New and updated cards relative to the requested snapshot." if delta else AGENDA_LEAD,
        "",
        f"Coverage: {coverage_text(payload)}. Snapshot `{payload['snapshot_id']}`.",
    ]
    notes = limitation_notes(payload)
    if notes:
        lines += ["", "⚠️ " + "; ".join(notes) + "."]
    lines += ["", *(_md_text(line) for line in comparison_lines(payload))]
    lines += _md_source_posts(payload)
    if not payload["stories"]:
        if not delta:
            lines += ["", EMPTY_AGENDA]
        lines += _md_extras(payload)
        lines += _md_footer(payload)
        return "\n".join(lines) + "\n"
    for index, card in enumerate(payload["stories"], 1):
        lines += ["", "---", ""]
        lines += _md_card_head(card, f"## {index}. {_md_text(card['title'])}")
        for claim in card["claims"][:CARD_QUOTES]:
            lines += _md_quote(claim)
        lines += _md_discussion(card, full=False)
    lines += _md_extras(payload)
    lines += _md_footer(payload)
    return "\n".join(lines) + "\n"


def _md_source_posts(payload: dict) -> list[str]:
    posts = payload.get("source_posts") or {}
    if not any(posts.values()):
        return []
    lines = [
        "",
        "## Fresh posts from X and Reddit",
        "",
        "Single-source posts; not independent confirmation.",
    ]
    for source, label in (("x", "X"), ("reddit", "Reddit")):
        if group := posts.get(source):
            lines += ["", f"### {label}"]
            lines += [
                f"- {short_time(post['published_at'])} [{_md_text(post['channel'])}]"
                f"(<{_md_url(post['link'])}>): **{_md_text(post['title'])}**"
                + (f" — {_md_text(post['text'])}" if post["text"] != post["title"] else "")
                for post in group
            ]
    return lines


def _md_footer(payload: dict) -> list[str]:
    lines = [
        "",
        "---",
        "",
        "_Quotes from non-English posts and comments are machine-translated. "
        "Copies are posts that repeat an earlier source's text near-verbatim; "
        "they add reach, not confirmation. Prices are context, not cause._",
    ]
    trust = trust_line(payload)
    if trust:
        lines += ["", trust]
    return lines


def _md_extras(payload: dict) -> list[str]:
    lines: list[str] = []
    leads = payload.get("lead_channels") or []
    if leads:
        lines += ["", "---", "", "## ⚡ First to report"]
        lines += [
            f"- **{_md_text(lead['channel'])}** — first on {lead['stories_first']} "
            f"{'story' if lead['stories_first'] == 1 else 'stories'}, {head_start(lead)}"
            for lead in leads
        ]
    upcoming = payload.get("upcoming") or []
    if upcoming:
        lines += ["", "## 📅 On the calendar"]
        lines += [
            f"- {_md_text(card['title'])} ({channel_count(card['current_channels'])})"
            for card in upcoming
        ]
    return lines


def render_story_md(payload: dict) -> str:
    card = payload["story"]
    lines = _md_card_head(card, f"# {_md_text(card['title'])}")
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
            (
                f"- {short_time(pub['published_at'])} [{_md_text(pub['channel'])}]"
                f"(<{_md_url(pub['link'])}>)"
            )
            for pub in card["publications"]
        ]
    lines += ["", f"Snapshot `{payload['snapshot_id']}` · {coverage_text(payload)}."]
    return "\n".join(lines) + "\n"


def render_search_md(payload: dict) -> str:
    hits = payload.get("hits") or []
    lines = [f"- {_md_text(hit['title'])} (`{_md_text(hit['story_id'])}`)" for hit in hits]
    return "\n".join(lines) + ("\n" if lines else "No matching stories.\n")
