from __future__ import annotations

import re

_HOST_PREFIXES = (
    "https://t.me/",
    "http://t.me/",
    "https://telegram.me/",
    "http://telegram.me/",
    "t.me/",
    "telegram.me/",
)

# Telegram usernames are ``[A-Za-z0-9_]`` only (mirrors ``sources.py``).
_USERNAME = re.compile(r"[A-Za-z0-9_]+")

# A stale private-post link ``t.me/id:<digits>/<rest>`` (built before the
# ``message_to_item`` ``t.me/c/...`` fix). Captures host, numeric id, and tail.
_STALE_ID_LINK = re.compile(r"^(https?://(?:t|telegram)\.me/)id:(\d+)(/.*)$")


def normalize_channel_ref(value: str) -> str:
    """Normalize a channel reference to ``@username``.

    Accepts ``@username``, bare ``username``, and public ``t.me``/``telegram.me``
    links. Private invite links (``t.me/+...`` or ``t.me/joinchat/...``) cannot
    be reduced to a username and are returned verbatim so Telethon can resolve
    the invite. Raises ``ValueError`` on empty input.
    """
    ref = value.strip()
    if not ref:
        raise ValueError("empty channel reference")

    lowered = ref.lower()
    for prefix in _HOST_PREFIXES:
        if lowered.startswith(prefix):
            rest = ref[len(prefix) :]
            # invite links have no plain username — keep the whole URL
            if rest.startswith("+") or rest.lower().startswith("joinchat/"):
                return ref
            username = rest.strip("/").split("/")[0]
            return f"@{username}"

    if ref.startswith("@"):
        return ref
    if ref.startswith("id:"):
        return ref
    return f"@{ref}"


def public_url_for_ref(ref: str) -> str | None:
    """Return ``https://t.me/<username>`` for a public ref, else ``None``.

    Deliberately strict for the render path: ``ref`` is an already-normalized
    channel reference (``@username`` or ``id:NNN``), not an arbitrary pasted
    link. A single leading ``@`` is stripped; the remainder must be a *whole*
    Telegram username (``[A-Za-z0-9_]+``). Anything URL-shaped, private
    (``id:NNN``), an invite link, or otherwise malformed yields ``None`` —
    private channels have no public handle, so no working link exists.

    Do NOT reuse this as a general "make a public Telegram URL" helper without
    revisiting that scope (URL-shaped input returning ``None`` is by design).
    """
    name = ref.strip()
    if name.startswith("@"):
        name = name[1:]
    if not _USERNAME.fullmatch(name):
        return None
    return f"https://t.me/{name}"


def repair_message_link(url: str) -> str:
    """Repair a stale ``t.me/id:<NNN>/<msg>`` link to ``t.me/c/<NNN>/<msg>``.

    Private-post links built before the ``message_to_item`` fix used the
    malformed ``id:`` form, which Telegram cannot open. Only that exact shape is
    rewritten; already-correct (``t.me/c/...``, ``t.me/<user>/...``), empty, or
    unknown-host URLs are returned unchanged.
    """
    return _STALE_ID_LINK.sub(r"\1c/\2\3", url)
