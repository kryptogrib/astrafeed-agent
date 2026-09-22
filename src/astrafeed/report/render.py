from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from html import escape

from astrafeed.report.dedup import MergedItem, _ItemKey
from astrafeed.report.events import EventBlock
from astrafeed.report.plan import ReportPlan
from astrafeed.report.trace import (
    RenderedPoint,
    RenderObserver,
    event_item_ids,
    event_material_keys,
    item_ids_of,
    material_keys_of,
)

_log = logging.getLogger(__name__)

__all__ = ["EventBlock", "render_report"]


# Pinned blocks plus orphan MergedItems. An unknown type raises (fail closed).
ReportRenderable = MergedItem | EventBlock


def _render_renderable(
    block: ReportRenderable,
    *,
    subfacts_max: int,
    observer: RenderObserver | None = None,
) -> str:
    """Type-keyed dispatch for a pinned renderable. Fail closed: an unsupported
    renderable type RAISES (never a silent no-op) so an unhandled producer surfaces
    loudly instead of dropping its block from the report. A wired arm may also raise
    on an invalid block (e.g. an EventBlock with no headline/sources); the caller
    reverts such a block to its member bullets so nothing is ever dropped."""
    if isinstance(block, MergedItem):
        text = _item_block(block)
        if observer is not None:
            observer(
                point=RenderedPoint(
                    kind="item",
                    item_ids=item_ids_of(block),
                    material_keys=material_keys_of(block),
                    text=text,
                )
            )
        return text
    if isinstance(block, EventBlock):
        text = _event_block(block, subfacts_max=subfacts_max)
        if observer is not None:
            shown = tuple(gist for gist, _link in block.subfacts[:subfacts_max] if gist)
            dropped = max(0, len(block.subfacts) - subfacts_max)
            observer(
                point=RenderedPoint(
                    kind="event",
                    item_ids=event_item_ids(block),
                    material_keys=event_material_keys(block),
                    subfacts=shown,
                    subfacts_dropped=dropped,
                    text=text,
                )
            )
        return text
    raise TypeError(f"unsupported ReportRenderable: {type(block).__name__}")


def _headline(m: MergedItem) -> str:
    """The gist itself is the tappable link to its primary (first) source post.
    One unambiguous link per item — no separate, easy-to-miss link line. The
    bullet/🔥 mark is owned by `_item_block`, so every item is prefixed the same."""
    gist = escape(m.gist) if m.gist else "(no text)"
    primary = m.sources[0][1] if m.sources else ""
    if primary:
        return f'<a href="{escape(primary)}">{gist}</a>'
    return gist


# importance (1..5) at or above which an item is flagged hot. Absolute, not
# per-group, so a 🔥 means the same thing everywhere in the report.
_FIRE_THRESHOLD = 4


def _footer(m: MergedItem) -> str:
    """Source line under the headline, shown only when the item was merged from
    several sources. The first source is already the headline link, so it is a
    plain italic handle; additional sources become their own links."""
    if len(m.sources) <= 1:
        return ""
    segments: list[str] = []
    for idx, (handle, link) in enumerate(m.sources):
        if idx == 0:
            segments.append(f"<i>{escape(handle)}</i>")
        else:
            segments.append(f'<a href="{escape(link)}">{escape(handle)}</a>')
    return " · ".join(segments)


def _item_block(m: MergedItem) -> str:
    bullet = "🔥" if m.importance >= _FIRE_THRESHOLD else "▪️"
    lines = [f"{bullet} {_headline(m)}"]
    footer = _footer(m)
    if footer:
        lines.append(footer)
    return "\n".join(lines)


def _event_footer(block: EventBlock) -> str:
    """Source line for a merged cross-channel event: link EVERY corroborating
    source (handle → its post). Unlike ``_footer`` — which hides on a single
    source and renders the first source as a plain italic handle — an event
    exists precisely *because* multiple channels reported it, so each source must
    stay reachable. Code owns all links/escaping."""
    links = " · ".join(
        f'<a href="{escape(link)}">{escape(handle)}</a>' for handle, link in block.sources
    )
    if len(block.sources) < 2:
        # One source is not corroboration; a "1 mention" badge would only add
        # noise to what is effectively an ordinary bullet.
        return links
    return f"🔁 {_mentions(len(block.sources))} · {links}"


def _mentions(n: int) -> str:
    return f"{n} mention" if n == 1 else f"{n} mentions"


def _event_block(block: EventBlock, *, subfacts_max: int) -> str:
    """Render a merged cross-channel event: a linked headline, then up to
    ``subfacts_max`` verbatim ``distinct``-framed subfact lines (each linked to its
    own source post), then the all-source footer. Raises ``ValueError`` on an
    invalid block (no headline or no sources) so the caller can revert it to its
    member bullets — a merged event is never silently dropped.

    ``block.subfacts`` is already headline-free (``events._build_block`` excludes the
    headline member), so the cap below means exactly "N rendered subfact lines"."""
    if not block.headline_gist or not block.sources:
        raise ValueError("EventBlock missing headline or sources")
    bullet = "🔥" if block.importance >= _FIRE_THRESHOLD else "▪️"
    if block.headline_link:
        headline = f'<a href="{escape(block.headline_link)}">{escape(block.headline_gist)}</a>'
    else:
        headline = escape(block.headline_gist)
    lines = [f"{bullet} {headline}"]
    for gist, link in block.subfacts[:subfacts_max]:
        if not gist:
            continue
        if link:
            lines.append(f'• <a href="{escape(link)}">{escape(gist)}</a>')
        else:
            lines.append(f"• {escape(gist)}")
    footer = _event_footer(block)
    if footer:
        lines.append(footer)
    return "\n".join(lines)


def _revert_to_members(
    block: ReportRenderable, member_lookup: Mapping[_ItemKey, MergedItem]
) -> list[MergedItem] | None:
    """Reconstruct a failed pinned block's member ``MergedItem``s (by stable key)
    so it renders as its original bullets instead of vanishing. Returns ``None``
    when reversal is impossible (no members known), so the caller re-raises — fail
    closed, never a silent drop."""
    if not isinstance(block, EventBlock):
        return None
    members = [member_lookup[k] for k in block.member_item_ids if k in member_lookup]
    if len(members) != len(block.member_item_ids):
        # A member key is missing from the lookup — a partial revert still beats a
        # silent drop, but it MUST surface: this is the single-news-never-lost path,
        # so a future refactor that breaks the lookup can't quietly lose news.
        missing = [k for k in block.member_item_ids if k not in member_lookup]
        _log.warning(
            "partial EventBlock revert: %d/%d members missing from lookup (%s)",
            len(missing),
            len(block.member_item_ids),
            missing,
        )
    return members or None


def render_report(
    pinned_blocks: Sequence[ReportRenderable],
    plan: ReportPlan,
    orphans: Sequence[MergedItem],
    *,
    hidden_count: int,
    run_time: datetime,
    language: str,
    window_hours: int = 24,
    event_subfacts_max: int = 4,
    member_lookup: Mapping[_ItemKey, MergedItem] | None = None,
    observer: RenderObserver | None = None,
) -> list[str]:
    """Render to a list of HTML 'parts' (fed to split_messages). Render order:
    header → ``pinned_blocks`` (code-ordered, dispatched by renderable type) →
    plan groups over ``orphans`` (a ``ReportGroup.item_ids`` string indexes into
    ``orphans``) → footer. Code owns links/escaping; the model owns only order and
    prose. `language` is accepted for future localization (v1 strings EN).

    The header's "key" count is the total of important units actually shown —
    ``len(orphans) + len(pinned_blocks)`` — because a promoted ``EventBlock`` is one
    important unit that no longer appears among the orphan bullets. With no pinned
    blocks (event merge off/empty) this is exactly ``len(orphans)`` as before.

    Reversibility: if a pinned block's render arm raises (an invalid block), it
    falls back to its member ``MergedItem`` bullets via ``member_lookup`` so no Item
    is dropped; a block with no recoverable members re-raises (fail closed).

    Known trade-off on the render-time revert path: ``important`` is computed ONCE,
    before any block renders, so a reverted block still counts as a single unit even
    though it expands to N member bullets, and those reverted bullets render here in
    the pinned position WITHOUT their interest-group context (header/insight). This
    is accepted: render-time revert is the rare unexpected-raise path (promotion-time
    validation already moves invalid blocks' members back into ``orphans``, where
    they regain group context and the count is exact); correctness of "never drop a
    news item" outweighs a momentarily off-by-N header on that path."""
    lookup = member_lookup or {}
    important = len(orphans) + len(pinned_blocks)
    header = f"🗞 Astrafeed — {run_time:%Y-%m-%d %H:%M} UTC · last {window_hours}h · {important} key"
    if hidden_count:
        header += f" ({hidden_count} hidden)"
    parts: list[str] = [header]
    for block in pinned_blocks:
        try:
            parts.append(
                _render_renderable(block, subfacts_max=event_subfacts_max, observer=observer)
            )
        except Exception:
            members = _revert_to_members(block, lookup)
            if members is None:
                raise
            for m in members:
                text = _item_block(m)
                if observer is not None:
                    observer(
                        point=RenderedPoint(
                            kind="reverted",
                            item_ids=item_ids_of(m),
                            material_keys=material_keys_of(m),
                            text=text,
                        )
                    )
                parts.append(text)
    if plan.overview:
        parts.append("🎯 " + escape(plan.overview))

    for g in plan.groups:
        if not g.item_ids:
            continue
        blocks = [
            _render_renderable(orphans[int(i)], subfacts_max=event_subfacts_max, observer=observer)
            for i in g.item_ids
        ]
        body = f"<b>{escape(g.title)}</b>\n\n" + "\n\n".join(blocks)
        if g.insight:
            body += "\n\n💡 " + escape(g.insight)
        parts.append(body)

    if hidden_count:
        parts.append(f"— {hidden_count} less important items hidden")
    return parts
