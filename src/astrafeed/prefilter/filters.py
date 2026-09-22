from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from astrafeed.domain import Item

_log = logging.getLogger(__name__)


class PrefilterObserver(Protocol):
    """Audit hook: called once per item with the prefilter outcome.

    reason is None when kept, else one of "length" | "blacklist" | "regex".
    """

    def __call__(self, *, item: Item, kept: bool, reason: str | None) -> None: ...


@dataclass(frozen=True)
class PrefilterConfig:
    min_length: int = 0
    blacklist_keywords: tuple[str, ...] = ()
    drop_regexes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # normalize lists -> tuples so the config is hashable/frozen-safe
        object.__setattr__(self, "blacklist_keywords", tuple(self.blacklist_keywords))
        object.__setattr__(self, "drop_regexes", tuple(self.drop_regexes))


def _drop_reason(item: Item, cfg: PrefilterConfig, compiled: list[re.Pattern]) -> str | None:
    """Return the drop reason, or None when the item should be kept."""
    text = item.text or ""
    if len(text.strip()) < cfg.min_length:
        return "length"
    low = text.lower()
    if any(kw.lower() in low for kw in cfg.blacklist_keywords):
        return "blacklist"
    if any(p.search(text) for p in compiled):
        return "regex"
    return None


def prefilter(
    items: list[Item],
    cfg: PrefilterConfig,
    *,
    observer: PrefilterObserver | None = None,
) -> list[Item]:
    compiled = [re.compile(r) for r in cfg.drop_regexes]
    survivors = []
    for item in items:
        reason = _drop_reason(item, cfg, compiled)
        if observer is not None:
            observer(item=item, kept=reason is None, reason=reason)
        if reason is None:
            survivors.append(item)
        else:
            _log.debug(
                "prefilter drop: id=%s reason=%s text=%r",
                item.external_id,
                reason,
                item.text[:80],
            )
    return survivors
