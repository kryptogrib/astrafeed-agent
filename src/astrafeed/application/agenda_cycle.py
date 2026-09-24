"""Agenda cycle: collect → concurrent extraction → ordered assignment → snapshot.

HTTP handlers never enter this module. Paid calls stay in extract/embed/assign.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Literal, Protocol

from astrafeed.application.agenda_assign import assign_speculative_batch
from astrafeed.application.agenda_extract import analyze_publication
from astrafeed.application.agenda_query import health_payload
from astrafeed.application.agenda_snapshot import build_snapshot, publish_snapshot
from astrafeed.domain.agenda import (
    CLASSIFIER_VERSION,
    LOOKBACK,
    ExtractionResult,
    PublicationVersion,
    Snapshot,
    analysis_reuse_key,
    publication_id,
    text_hash,
    windows_at,
)
from astrafeed.domain.models import Item
from astrafeed.domain.spend_budget import BudgetExceeded
from astrafeed.ports.agenda import AgendaStore, Embedder, OpenExtractor, StoryAssigner

CollectFn = Callable[[datetime, datetime], Awaitable[None]]
_log = logging.getLogger(__name__)


class WindowReader(Protocol):
    async def read_window(self, source_id: int, start: datetime, end: datetime) -> list[Item]: ...

    async def coverage(self, source_id: int, start: datetime, end: datetime): ...


def _publication(source_id: int, item: Item, detected_at: datetime) -> PublicationVersion:
    return PublicationVersion(
        publication_id=publication_id(source_id, item.external_id),
        source_id=source_id,
        external_id=item.external_id,
        text=item.text,
        text_hash=text_hash(item.text),
        published_at=item.timestamp,
        detected_at=detected_at,
        channel_ref=item.channel_ref,
        link=item.link,
    )


def _partial_is_publishable(partial: Snapshot, previous: Snapshot | None) -> bool:
    if previous is None or not previous.agenda:
        return True
    if not partial.agenda:
        return False
    partial_time = getattr(partial, "t", None)
    previous_time = getattr(previous, "t", None)
    analyzed_at = getattr(partial, "analyzed_at", None)
    previous_analyzed_at = getattr(previous, "analyzed_at", None)
    return (
        partial_time is not None
        and previous_time is not None
        and (
            partial_time > previous_time
            or (
                partial_time == previous_time
                and analyzed_at is not None
                and previous_analyzed_at is not None
                and analyzed_at > previous_analyzed_at
            )
        )
    ) or len(partial.agenda) >= len(previous.agenda)


async def restore_useful_snapshot(store: AgendaStore) -> bool:
    latest = await store.get_snapshot(None)
    if latest is None or latest.agenda or "processing_in_progress" not in latest.limitations:
        return False
    useful = await store.latest_nonempty_snapshot()
    if useful is None:
        return False
    await publish_snapshot(store, useful)
    return True


async def ingest_publications(
    store: AgendaStore,
    reader: WindowReader,
    source_ids: Sequence[int],
    start: datetime,
    end: datetime,
    now: datetime,
) -> None:
    for source_id in source_ids:
        items = await reader.read_window(source_id, start, end)
        for item in items:
            if not (start <= item.timestamp < end):
                continue
            incoming = _publication(source_id, item, now)
            previous = await store.record_publication(incoming)
            latest = await store.latest_publication(incoming.publication_id)
            if latest is None:
                continue
            if previous is None:
                await store.enqueue(latest.publication_id, "new")
            elif previous.text_hash != latest.text_hash:
                await store.enqueue(latest.publication_id, "edited")


async def _coverage_states(
    store: AgendaStore,
    reader: WindowReader,
    source_ids: Sequence[int],
    now: datetime,
) -> dict[int, dict[str, bool]]:
    current, previous = windows_at(now)
    queued = set(await store.queued_ids())
    lookback_pubs = await store.publications_in(previous[0], current[1])
    queued_sources = {pub.source_id for pub in lookback_pubs if pub.publication_id in queued}
    states: dict[int, dict[str, bool]] = {}
    for source_id in source_ids:
        cur = await reader.coverage(source_id, current[0], current[1])
        prev = await reader.coverage(source_id, previous[0], previous[1])
        states[source_id] = {
            "current_complete": bool(cur.complete),
            "previous_complete": bool(prev.complete),
            "processed": source_id not in queued_sources,
        }
    return states


async def run_cycle(
    store: AgendaStore,
    *,
    reader: WindowReader,
    source_ids: Sequence[int],
    extractor: OpenExtractor,
    embedder: Embedder,
    assigner: StoryAssigner,
    now: datetime,
    collect: CollectFn | None = None,
    extract_concurrency: int = 12,
    assign_concurrency: int = 16,
    backfill_batch_size: int = 128,
    assignment_mode: Literal["auto", "strict", "relaxed"] = "auto",
    merge_cosine_threshold: float = 0.92,
    collection_window: timedelta = LOOKBACK,
    partial_snapshot_every: int = 200,
    partial_snapshot_seconds: float = 600.0,
    max_posts_per_cycle: int | None = None,
    ingest: bool = True,
) -> Snapshot | None:
    if not source_ids:
        raise ValueError("agenda requires at least one resolved source")
    if extract_concurrency < 1:
        raise ValueError("extract_concurrency must be positive")
    if assign_concurrency < 1:
        raise ValueError("assign_concurrency must be positive")
    if backfill_batch_size < 1:
        raise ValueError("backfill_batch_size must be positive")
    if assignment_mode not in {"auto", "strict", "relaxed"}:
        raise ValueError("invalid assignment_mode")
    if collection_window < LOOKBACK:
        raise ValueError("collection_window must cover both comparison windows")
    if partial_snapshot_every < 1 or partial_snapshot_seconds <= 0:
        raise ValueError("partial snapshot thresholds must be positive")
    if max_posts_per_cycle is not None and max_posts_per_cycle < 1:
        raise ValueError("max_posts_per_cycle must be positive")
    cycle_started = perf_counter()
    state = await store.get_cycle_state()
    as_of = now if ingest else state.last_collect_at or now
    state.phase = "collect"
    state.budget_blocked = False
    await store.set_cycle_state(state)
    start = as_of - collection_window
    source_set = set(source_ids)
    try:
        if collect is not None:
            await collect(start, now)
        if ingest:
            await ingest_publications(store, reader, source_ids, start, now, now)
        if await restore_useful_snapshot(store):
            _log.info("agenda restored previous nonempty snapshot during backfill")
        if ingest:
            state.last_collect_at = now
            state.first_collect_done = True
        state.phase = "analyze"
        await store.set_cycle_state(state)

        queued = set(await store.retryable_ids())
        pending = [
            pub
            for pub in await store.publications_in(datetime.min.replace(tzinfo=UTC), as_of)
            if pub.publication_id in queued and pub.source_id in source_set
        ]
        if max_posts_per_cycle is not None:
            current_start = as_of - timedelta(hours=24)
            previous_start = as_of - LOOKBACK
            pending.sort(
                key=lambda pub: (
                    0
                    if pub.published_at >= current_start
                    else 1
                    if pub.published_at >= previous_start
                    else 2,
                    pub.published_at,
                    pub.publication_id,
                )
            )
        else:
            pending.sort(key=lambda pub: (pub.published_at, pub.publication_id))
        pending_count = len(pending)
        remaining_backfill = (
            max_posts_per_cycle is not None and pending_count > max_posts_per_cycle
        )
        if max_posts_per_cycle is not None:
            pending = pending[:max_posts_per_cycle]
        strict_assignment = assignment_mode == "strict" or (
            assignment_mode == "auto" and pending_count < 128
        )
        batch_size = extract_concurrency if strict_assignment else backfill_batch_size
        semaphore = asyncio.Semaphore(extract_concurrency)
        reuse_locks: dict[str, asyncio.Lock] = {}
        extract_seconds = 0.0
        assign_seconds = 0.0
        speculative_reused = 0
        speculative_retried = 0
        pipeline_started = perf_counter()
        last_partial_count = 0
        last_partial_time = pipeline_started

        async def extract_one(publication: PublicationVersion) -> ExtractionResult:
            nonlocal extract_seconds
            key = analysis_reuse_key(publication.text_hash, CLASSIFIER_VERSION)
            async with reuse_locks.setdefault(key, asyncio.Lock()), semaphore:
                started = perf_counter()
                try:
                    return await analyze_publication(store, extractor, publication)
                finally:
                    extract_seconds += perf_counter() - started

        _log.info(
            "agenda analyze started posts=%d concurrency=%d", len(pending), extract_concurrency
        )
        try:
            for offset in range(0, len(pending), batch_size):
                batch = pending[offset : offset + batch_size]
                tasks = [asyncio.create_task(extract_one(pub)) for pub in batch]
                try:
                    jobs = []
                    for publication, task in zip(batch, tasks, strict=True):
                        extraction = await task
                        if extraction.status == "error":
                            continue
                        if extraction.status == "empty":
                            await store.mark_processed(publication.publication_id)
                            continue
                        jobs.append((publication, extraction))
                    started = perf_counter()
                    try:
                        reused, retried = await assign_speculative_batch(
                            store,
                            embedder,
                            assigner,
                            jobs,
                            concurrency=assign_concurrency,
                            strict=strict_assignment,
                            merge_cosine_threshold=merge_cosine_threshold,
                        )
                        speculative_reused += reused
                        speculative_retried += retried
                    finally:
                        assign_seconds += perf_counter() - started
                    _log.info(
                        "agenda analyze progress=%d/%d extract_seconds=%.1f "
                        "assign_seconds=%.1f wall_seconds=%.1f reused=%d retried=%d",
                        offset + len(batch),
                        len(pending),
                        extract_seconds,
                        assign_seconds,
                        perf_counter() - pipeline_started,
                        speculative_reused,
                        speculative_retried,
                    )
                    processed = offset + len(batch)
                    if processed < len(pending) and (
                        last_partial_count == 0
                        or processed - last_partial_count >= partial_snapshot_every
                        or perf_counter() - last_partial_time >= partial_snapshot_seconds
                    ):
                        partial_time = now + timedelta(seconds=perf_counter() - cycle_started)
                        coverage = await _coverage_states(store, reader, source_ids, as_of)
                        partial = await build_snapshot(
                            store,
                            as_of,
                            coverage,
                            collected_at=state.last_collect_at or now,
                            analyzed_at=partial_time,
                        )
                        limitation = "processing_in_progress"
                        partial_id = f"{partial.snapshot_id}-p{processed}"
                        if max_posts_per_cycle is not None:
                            partial_id += f"-{partial_time.strftime('%H%M%S%f')}"
                        partial = replace(
                            partial,
                            snapshot_id=partial_id,
                            published_at=partial_time,
                            limitations=(*partial.limitations, limitation),
                            coverage=replace(
                                partial.coverage,
                                limitations=(*partial.coverage.limitations, limitation),
                            ),
                        )
                        previous = await store.get_snapshot(None)
                        if _partial_is_publishable(partial, previous):
                            await publish_snapshot(store, partial)
                            state.last_partial_at = partial_time
                            state.queue_depth = await store.queue_depth()
                            await store.set_cycle_state(state)
                            _log.info(
                                "agenda partial snapshot %s queue=%d",
                                partial.snapshot_id,
                                partial.queue_depth,
                            )
                        else:
                            _log.info(
                                "agenda partial snapshot skipped stories=%d previous=%d",
                                len(partial.agenda),
                                len(previous.agenda) if previous is not None else 0,
                            )
                        last_partial_count = processed
                        last_partial_time = perf_counter()
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            _log.info(
                "agenda analyze posts=%d extract_seconds=%.1f assign_seconds=%.1f "
                "wall_seconds=%.1f extract_concurrency=%d assign_concurrency=%d "
                "batch_size=%d reused=%d retried=%d mode=%s",
                len(pending),
                extract_seconds,
                assign_seconds,
                perf_counter() - pipeline_started,
                extract_concurrency,
                assign_concurrency,
                batch_size,
                speculative_reused,
                speculative_retried,
                "strict" if strict_assignment else "relaxed",
            )

        finished_at = now + timedelta(seconds=perf_counter() - cycle_started)
        state.last_analyze_at = finished_at
        state.phase = "snapshot"
        await store.set_cycle_state(state)
        coverage = await _coverage_states(store, reader, source_ids, as_of)
        snapshot = await build_snapshot(
            store,
            as_of,
            coverage,
            collected_at=state.last_collect_at or now,
            analyzed_at=finished_at,
        )
        snapshot = replace(snapshot, published_at=finished_at)
        if remaining_backfill:
            snapshot = replace(
                snapshot,
                snapshot_id=(
                    f"{snapshot.snapshot_id}-p{len(pending)}-"
                    f"{finished_at.strftime('%H%M%S%f')}"
                ),
                limitations=(*snapshot.limitations, "processing_in_progress"),
                coverage=replace(
                    snapshot.coverage,
                    limitations=(*snapshot.coverage.limitations, "processing_in_progress"),
                ),
            )
            previous = await store.get_snapshot(None)
            if _partial_is_publishable(snapshot, previous):
                await publish_snapshot(store, snapshot)
                state.last_partial_at = finished_at
        else:
            await publish_snapshot(store, snapshot)
        state.phase = "idle"
        if not remaining_backfill:
            state.last_success_at = finished_at
            state.last_full_success_at = finished_at
        state.last_error = ""
        state.queue_depth = await store.queue_depth()
        await store.set_cycle_state(state)
        return snapshot
    except BudgetExceeded as exc:
        state.phase = "blocked"
        state.budget_blocked = True
        state.last_error = str(exc)
        state.queue_depth = await store.queue_depth()
        await store.set_cycle_state(state)
        return None
    except Exception as exc:
        state.phase = "idle"
        state.last_error = type(exc).__name__
        state.queue_depth = await store.queue_depth()
        await store.set_cycle_state(state)
        raise


async def cycle_health(store: AgendaStore, *, now: datetime, commit: str) -> dict:
    return await health_payload(store, now=now, commit=commit)
