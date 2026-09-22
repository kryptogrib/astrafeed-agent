from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from astrafeed.domain import Channel, Interest, Item, Route, Verdict
from astrafeed.domain.progress import processed_item_signature
from astrafeed.domain.report import TransientScoringError, is_transient_scoring_failure
from astrafeed.domain.spend_budget import BudgetExceeded
from astrafeed.ports import LLMClient, Repository, Source
from astrafeed.prefilter.dedup import DedupConfig, Deduper, signatures_for
from astrafeed.prefilter.filters import PrefilterConfig, prefilter

_log = logging.getLogger(__name__)


@dataclass
class TickResult:
    collected: int = 0
    scored: int = 0
    reported: int = 0
    dropped: int = 0


@dataclass
class _ChannelWork:
    """Per-channel state carried from the collect phase to the commit phase."""

    channel: Channel
    items: Sequence[Item]
    survivors: list[Item]
    verdicts: list[Verdict] = field(default_factory=list)


class Pipeline:
    """Core orchestrator: collect -> prefilter -> dedup -> score -> enqueue.

    One Verdict per Item (ADR-0001); one score() call per tick (ADR-0002).
    Free deterministic Pre-filters and conservative textual dedup gate the paid
    model so dropped/duplicate Items never reach score()."""

    def __init__(
        self,
        *,
        source: Source,
        llm: LLMClient,
        repo: Repository,
        prefilter_config: PrefilterConfig | None = None,
        deduper: Deduper | None = None,
        dedup_config: DedupConfig | None = None,
    ) -> None:
        self._source = source
        self._llm = llm
        self._repo = repo
        self._prefilter_config = prefilter_config or PrefilterConfig()
        self._deduper = deduper or Deduper()
        self._dedup_config = dedup_config or DedupConfig()

    async def run_tick(self, *, ignore_cursor: bool = False) -> TickResult:
        """Run one tick. ``ignore_cursor`` re-reads each channel from the start of
        the Source's window and skips persistent dedup (one-shot briefs)."""
        result = TickResult()
        pending = await self._collect(result, ignore_cursor=ignore_cursor)
        await self._score(pending, result)
        await self._commit(pending, result)
        return result

    async def _collect(self, result: TickResult, *, ignore_cursor: bool) -> list[_ChannelWork]:
        # In-tick dedup is scoped to this tick; persistent dedup is the repo's.
        self._deduper.reset()
        pending: list[_ChannelWork] = []
        for channel in await self._repo.list_channels():
            assert channel.id is not None
            since = None if ignore_cursor else await self._repo.get_watermark(channel.id)
            try:
                items = await self._source.fetch_new_items(channel, since)
            except Exception:
                _log.exception("channel=%s fetch failed; skipping", channel.telegram_ref)
                continue
            if not items:
                continue
            result.collected += len(items)
            # record_seen=False: the persistent dedup write is deferred to the
            # commit phase, so a score failure leaves dedup state and the
            # watermark untouched (at-least-once scoring; ADR-0002).
            survivors = await self._dedup(
                prefilter(items, self._prefilter_config),
                persistent=not ignore_cursor,
            )
            _log.debug(
                "channel=%s fetched=%d survivors=%d",
                channel.telegram_ref,
                len(items),
                len(survivors),
            )
            pending.append(_ChannelWork(channel=channel, items=items, survivors=survivors))
        return pending

    async def _score(self, pending: list[_ChannelWork], result: TickResult) -> None:
        pairs = [(item, work) for work in pending for item in work.survivors]
        if not pairs:
            return
        interests: list[Interest] = list(await self._repo.global_interests())
        try:
            verdicts = await self._llm.score([item for item, _ in pairs], interests)
        except BudgetExceeded:
            raise
        except Exception as exc:
            if is_transient_scoring_failure(exc) and not isinstance(exc, TransientScoringError):
                raise TransientScoringError(str(exc)) from exc
            # A structural failure surviving the re-ask budget must not advance
            # watermarks or record dedup signatures: re-raise so nothing commits.
            raise
        result.scored += len(verdicts)
        for (_, work), verdict in zip(pairs, verdicts, strict=True):
            work.verdicts.append(verdict)

    async def _commit(self, pending: Sequence[_ChannelWork], result: TickResult) -> None:
        # Order matters: enqueue FIRST, then record_seen, then watermark. If
        # enqueue raises, no dedup signatures are recorded and the watermark
        # stays put, so the item is re-fetched rather than silently lost.
        for work in pending:
            channel_id = work.channel.id
            assert channel_id is not None
            for verdict in work.verdicts:
                if verdict.route is Route.DROP:
                    result.dropped += 1
                else:
                    await self._repo.enqueue_report(verdict)
                    result.reported += 1
            await self._record_seen(work.survivors)
            watermark = max(i.timestamp for i in work.items)
            await self._repo.record_seen(
                {processed_item_signature(channel_id, i.external_id) for i in work.items},
                watermark,
            )
            await self._repo.set_watermark(channel_id, watermark)

    async def _dedup(self, items: list[Item], *, persistent: bool) -> list[Item]:
        if not items:
            return []
        since = min(i.timestamp for i in items) - self._dedup_config.window
        return await self._deduper.filter(
            items,
            repo=self._repo if persistent else None,
            since=since,
            record_seen=False,
        )

    async def _record_seen(self, survivors: Sequence[Item]) -> None:
        """Persist dedup signatures for scored survivors (deferred from _dedup)."""
        if not survivors:
            return
        sigs: set[str] = set()
        for item in survivors:
            sigs.update(signatures_for(item))
        await self._repo.record_seen(sigs, max(i.timestamp for i in survivors))
