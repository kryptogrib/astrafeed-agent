"""Markdown agenda and story reports rendered from a JSON payload."""

from __future__ import annotations

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


def _md_quote(item: dict) -> list[str]:
    return ["", f"> “{english_text(item)}” — [{item['channel']}]({item['link']})"]


def _md_card_head(card: dict, heading: str) -> list[str]:
    lines = [
        heading,
        "",
        f"**{count_text(card)}** · {growth_text(card)}  ",
        meta_text(card),
        "",
        card["explanation"],
    ]
    signal_lines = evidence_lines(card)
    if signal_lines:
        lines += [""] + [f"{line}  " for line in signal_lines]
    caveat = (card.get("signals") or {}).get("caveat_drop")
    if caveat:
        lines += [
            "",
            "⚠️ **Qualifier dropped in later wording** "
            f"(+{duration_text(caveat['minutes_later'])}):",
            f"- [{caveat['before_channel']}]({caveat['before_link']}): “{caveat['before_quote']}”",
            f"- [{caveat['after_channel']}]({caveat['after_link']}): “{caveat['after_quote']}”",
        ]
    channels = channel_links(card)
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
    lines += [f"- {point}" for point in discussion["points"]]
    for fact, comment in facts:
        source = (
            f" — [comments under {comment['channel']} post]({comment['link']})" if comment else ""
        )
        lines.append(f"- {fact}{source}")
        if full and comment:
            lines.append(f"  > “{english_text(comment, 'text')}”")
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
    lines += ["", *comparison_lines(payload)]
    lines += _md_source_posts(payload)
    if not payload["stories"]:
        if not delta:
            lines += ["", EMPTY_AGENDA]
        lines += _md_extras(payload)
        lines += _md_footer(payload)
        return "\n".join(lines) + "\n"
    for index, card in enumerate(payload["stories"], 1):
        lines += ["", "---", ""]
        lines += _md_card_head(card, f"## {index}. {card['title']}")
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
                f"- {short_time(post['published_at'])} [{post['channel']}]({post['link']}): "
                f"**{post['title']}**"
                + (f" — {post['text']}" if post["text"] != post["title"] else "")
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
            f"- **{lead['channel']}** — first on {lead['stories_first']} "
            f"{'story' if lead['stories_first'] == 1 else 'stories'}, {head_start(lead)}"
            for lead in leads
        ]
    upcoming = payload.get("upcoming") or []
    if upcoming:
        lines += ["", "## 📅 On the calendar"]
        lines += [
            f"- {card['title']} ({channel_count(card['current_channels'])})" for card in upcoming
        ]
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
            f"- {short_time(pub['published_at'])} [{pub['channel']}]({pub['link']})"
            for pub in card["publications"]
        ]
    lines += ["", f"Snapshot `{payload['snapshot_id']}` · {coverage_text(payload)}."]
    return "\n".join(lines) + "\n"
