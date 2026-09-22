from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from astrafeed.domain import Item
from astrafeed.textkey import text_hash as _text_hash

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DedupConfig:
    """How far back to look for seen signatures.

    Default 7 days — older can re-surface as genuinely new. Measured against
    Item.timestamp, not wall-clock (ADR-0002).
    """

    window: timedelta = timedelta(days=7)


class DedupObserver(Protocol):
    """Audit hook: called once per item with the dedup decision.

    decision: "kept" | "dropped". scope: "in-tick" | "persistent" | None.
    signature: the matched signature on a drop, else None.
    """

    def __call__(
        self,
        *,
        item: Item,
        decision: str,
        scope: str | None,
        signature: str | None,
    ) -> None: ...


_URL_RE = re.compile(r"https?://\S+")


def _urls(text: str) -> list[str]:
    return [u.rstrip(".,)") for u in _URL_RE.findall(text)]


def signatures_for(item: Item) -> set[str]:
    """All signatures for an Item: text-hash + each URL (no collision)."""
    sigs: set[str] = {_text_hash(item.text)}
    sigs.update(_urls(item.text))
    return sigs


class Deduper:
    """Conservative dedup: exact normalized-text hash + shared URL.

    In-tick dedup (issue 06) is preserved by the in-memory sets.
    Persistent dedup (issue 15) is opt-in via ``repo`` + ``since``.
    """

    def __init__(self, *, observer: DedupObserver | None = None) -> None:
        self._seen_hashes: set[str] = set()
        self._seen_urls: set[str] = set()
        self._observer = observer

    def reset(self) -> None:
        """Clear the in-tick (in-memory) dedup state, preserving the observer.

        In-tick dedup (issue 06) is scoped to a SINGLE tick; cross-tick dedup is
        the repo's persistent ``seen_signature`` job. The pipeline reuses one
        injected Deduper across ticks (e.g. to keep an audit observer), so it
        must reset the in-memory sets each tick — otherwise an item from an
        earlier tick is wrongly dropped as an "in-tick" duplicate, which would
        also swallow items deferred by a score failure (at-least-once)."""
        self._seen_hashes.clear()
        self._seen_urls.clear()

    def _emit(self, *, item: Item, decision: str, scope: str | None, signature: str | None) -> None:
        if self._observer is not None:
            self._observer(item=item, decision=decision, scope=scope, signature=signature)

    async def filter(
        self,
        items: list[Item],
        *,
        repo=None,
        since: datetime | None = None,
        record_seen: bool = True,
    ) -> list[Item]:
        """Filter duplicates.

        Without repo: pure in-memory (issue-06 behaviour unchanged).
        With repo + since: also queries seen_signature table for cross-tick dedup.

        record_seen=True (default): persist surviving signatures via record_seen
        (event-time = max timestamp of survivors). ONE batched query + ONE write.

        record_seen=False: check only (in-tick + persistent query), DO NOT write.
        Lets the caller defer the persistent write until AFTER a successful score,
        so a score failure neither advances the watermark nor records dedup state
        (at-least-once scoring; ADR-0002).
        """
        # --- in-tick pass (issue-06, always) ---
        in_tick_survivors: list[Item] = []
        for item in items:
            h = _text_hash(item.text)
            urls = _urls(item.text)
            if h in self._seen_hashes or any(u in self._seen_urls for u in urls):
                matched = (
                    h if h in self._seen_hashes else next(u for u in urls if u in self._seen_urls)
                )
                self._emit(item=item, decision="dropped", scope="in-tick", signature=matched)
                _log.debug("dedup drop (in-tick): id=%s", item.external_id)
                continue
            self._seen_hashes.add(h)
            self._seen_urls.update(urls)
            in_tick_survivors.append(item)

        if repo is None or since is None:
            for item in in_tick_survivors:
                self._emit(item=item, decision="kept", scope=None, signature=None)
            return in_tick_survivors

        # --- persistent pass (issue-15): ONE batched query ---
        # Build map: sig -> item (an item may have multiple sigs)
        candidate_sigs: dict[str, Item] = {}
        for item in in_tick_survivors:
            for sig in signatures_for(item):
                candidate_sigs[sig] = item

        already_seen = await repo.seen_signatures(set(candidate_sigs), since)

        # Drop items whose ANY signature is already seen
        dropped_items: set[int] = set()
        for sig, item in candidate_sigs.items():
            if sig in already_seen and id(item) not in dropped_items:
                dropped_items.add(id(item))
                self._emit(item=item, decision="dropped", scope="persistent", signature=sig)
                _log.debug("dedup drop (persistent): id=%s sig=%s", item.external_id, sig[:16])

        survivors = [i for i in in_tick_survivors if id(i) not in dropped_items]
        for item in survivors:
            self._emit(item=item, decision="kept", scope=None, signature=None)

        # --- ONE batched write (skipped when caller defers it) ---
        if record_seen and survivors:
            when = max(i.timestamp for i in survivors)
            new_sigs: set[str] = set()
            for item in survivors:
                new_sigs.update(signatures_for(item))
            await repo.record_seen(new_sigs, when)

        return survivors
