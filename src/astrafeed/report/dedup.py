from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from astrafeed.domain import Item, Verdict
from astrafeed.textkey import text_hash

_HANDLE_RE = re.compile(r"https?://t\.me/([^/]+)/")

_SourcePair = tuple[str, str]  # (channel_handle, link)
_ItemKey = tuple[str, str]  # (channel_ref, external_id) — stable member identity


def _channel_handle(link: str) -> str:
    m = _HANDLE_RE.match(link)
    return m.group(1) if m else link


def _source_pair(item: Item) -> _SourcePair:
    """Build the (label, link) pair for a report source. Private channels have no
    public @handle — their links are ``t.me/c/<id>/..`` so the regex yields the
    opaque ``c`` (legacy data may yield ``id:<n>``). In those cases prefer the
    channel's human name; public channels keep their @username handle."""
    handle = _channel_handle(item.link)
    if handle in ("c", "") or handle.startswith("id:"):
        handle = item.channel_name or handle
    return (handle, item.link)


@dataclass(frozen=True)
class MergedItem:
    gist: str
    importance: int
    interests: tuple[str, ...]
    sources: tuple[_SourcePair, ...]  # first-seen order
    cluster_id: str
    representative_item: Item | None = None
    # ``first_ts`` is the earliest member timestamp; ``anchor_link`` is the
    # representative member's post link; ``member_item_ids`` is the stable
    # ``(channel_ref, external_id)`` key of every member (a single-source item
    # carries just its own key), enabling a reversible cross-channel merge.
    # ``consumed_member_item_ids`` is set by ``assemble_events`` on items folded
    # into an EventBlock.
    first_ts: datetime | None = None
    anchor_link: str = ""
    member_item_ids: tuple[_ItemKey, ...] = ()
    consumed_member_item_ids: frozenset[_ItemKey] = field(default_factory=frozenset)
    # Structured "what happened" from the scorer ("actor|action|object"), used as
    # a recall route for rewrites that share no wording with the original. Empty
    # when the model omitted it — then only the lexical routes apply.
    event_key: str = ""


def dedup_for_report(verdicts: Sequence[Verdict]) -> list[MergedItem]:
    """Collapse verdicts whose normalized text matches into one MergedItem.
    importance = max; gist = highest-importance member's summary (verbatim, may
    be empty — never falls back to raw item.text, which would leak the raw post
    across the LLM boundary into the strong editor); interests = first-seen
    union; sources = all (handle, link); cluster_id = text hash.
    Order: first appearance of each cluster (stable)."""
    if not verdicts:
        return []
    order: list[str] = []
    groups: dict[str, list[Verdict]] = {}
    for v in verdicts:
        key = text_hash(v.item.text)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(v)

    out: list[MergedItem] = []
    for key in order:
        members = groups[key]
        top = max(members, key=lambda v: v.importance)
        interests: list[str] = []
        for v in members:
            for t in v.matched_interests:
                if t not in interests:
                    interests.append(t)
        sources: list[_SourcePair] = []
        for v in members:
            pair = _source_pair(v.item)
            if pair not in sources:
                sources.append(pair)
        member_item_ids = tuple((v.item.channel_ref, v.item.external_id) for v in members)
        first_ts = min(v.item.timestamp for v in members)
        out.append(
            MergedItem(
                gist=top.summary,
                importance=top.importance,
                interests=tuple(interests),
                sources=tuple(sources),
                cluster_id=key,
                representative_item=top.item,
                first_ts=first_ts,
                anchor_link=top.item.link,
                member_item_ids=member_item_ids,
                event_key=top.event_key,
            )
        )
    return out
