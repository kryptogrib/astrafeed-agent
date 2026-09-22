from __future__ import annotations

import re
from collections.abc import Iterable

from astrafeed.domain.models import Item
from astrafeed.domain.refs import normalize_channel_ref

# At most this many distinct source channels are retained per Source Lead.
SOURCE_REFS_CAP = 3

# Match t.me / telegram.me links with an optional scheme, capturing the path
# (plus any query/fragment) as a single run of non-whitespace characters. The
# leading lookbehind forces the host to start at a token boundary so substrings
# like ``list.me/x`` or ``example.com/t.me/x`` don't match.
_TME_LINK = re.compile(r"(?i)(?<![\w./])(?:https?://)?(?:t\.me|telegram\.me)/(\S+)")

# Telegram usernames are ``[A-Za-z0-9_]`` only.
_USERNAME = re.compile(r"[A-Za-z0-9_]+")


def _lead_from_link_path(path: str) -> str | None:
    """Normalize a captured ``t.me`` path to a lower-cased ``@username`` or None.

    Strips any query/fragment first (``normalize_channel_ref`` only splits on
    ``/``), then defers to it for deep-link collapse and invite rejection
    (invite links survive normalization verbatim, not starting with ``@``).
    Finally trims the username to its leading ``[A-Za-z0-9_]`` run so trailing
    punctuation (``t.me/foo.`` , ``(t.me/foo)``) doesn't leak into the ref, and
    lower-cases it (usernames are case-insensitive).
    """
    clean = path.split("?", 1)[0].split("#", 1)[0]
    if not clean:
        return None
    normalized = normalize_channel_ref(f"t.me/{clean}")
    if not normalized.startswith("@"):
        return None  # invite link
    match = _USERNAME.match(normalized[1:])
    if match is None:
        return None
    return f"@{match.group(0).lower()}"


def _norm_lower(ref: str) -> str:
    """Normalize a ref and lower-case it for case-insensitive Lead comparison.

    Casefolding is kept LOCAL to the Source Lead path; ``normalize_channel_ref``
    (shared with channel storage) is intentionally left untouched.
    """
    return normalize_channel_ref(ref).lower()


def merge_source_refs(existing: Iterable[str], new: str, cap: int = SOURCE_REFS_CAP) -> list[str]:
    """Append ``new`` to ``existing`` (order-preserving, deduped, capped).

    Telegram usernames are case-insensitive, so refs are lower-cased before the
    dedup/cap. Once ``cap`` distinct refs are retained, further ones are dropped
    (``times_seen`` still counts every observation — that bookkeeping lives in
    the repository upsert, not here)."""
    out = [r.lower() for r in existing]
    candidate = new.lower()
    if candidate not in out and len(out) < cap:
        out.append(candidate)
    return out


def extract_source_leads(item: Item, source_ref: str) -> set[str]:
    """Extract normalized Source Lead refs (lower-cased ``@username``) from an Item.

    Unifies two signals: the Item's ``forwarded_from_ref`` (a forward whose
    origin is a public channel) and real ``t.me/`` links mined from its text.
    Deep links collapse to the channel, query/fragment is stripped, invite
    links are dropped, bare ``@mentions`` are never mined, refs are lower-cased
    (usernames are case-insensitive), and any lead equal to the ``source_ref``
    is dropped as a self-reference (also case-insensitively).
    """
    self_ref = _norm_lower(source_ref)
    leads: set[str] = set()

    if item.forwarded_from_ref:
        leads.add(_norm_lower(item.forwarded_from_ref))

    for path in _TME_LINK.findall(item.text or ""):
        lead = _lead_from_link_path(path)
        if lead is not None:
            leads.add(lead)

    leads.discard(self_ref)
    return leads
