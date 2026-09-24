"""Sequential agenda cycle: collect → analyze posts → publish a snapshot.

HTTP handlers never enter this module. Paid calls stay in extract/embed/assign.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Protocol

from astrafeed.application.agenda_assign import assign_publication
from astrafeed.application.agenda_extract import analyze_publication
from astrafeed.application.agenda_query import health_payload
from astrafeed.application.agenda_snapshot import build_snapshot, publish_snapshot
from astrafeed.domain.agenda import (
    LOOKBACK,
    PublicationVersion,
    Snapshot,
    publication_id,
    text_hash,
    windows_at,
)
from astrafeed.domain.models import Item
from astrafeed.domain.spend_budget import BudgetExceeded
from astrafeed.ports.agenda import AgendaStore, Embedder, OpenExtractor, StoryAssigner

CollectFn = Callable[[datetime, datetime], Awaitable[None]]


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
) -> Snapshot | None:
    state = await store.get_cycle_state()
    state.phase = "collect"
    state.budget_blocked = False
    await store.set_cycle_state(state)
    start = now - LOOKBACK
    source_set = set(source_ids)
    try:
        if collect is not None:
            await collect(start, now)
        await ingest_publications(store, reader, source_ids, start, now, now)
        state.last_collect_at = now
        state.first_collect_done = True
        state.phase = "analyze"
        await store.set_cycle_state(state)

        pending: list[PublicationVersion] = []
        for publication_id_ in await store.queued_ids():
            latest = await store.latest_publication(publication_id_)
            if latest is not None and latest.source_id in source_set:
                pending.append(latest)
        pending.sort(key=lambda pub: (pub.published_at, pub.publication_id))
        for publication in pending:
            extraction = await analyze_publication(store, extractor, publication)
            if extraction.status == "error":
                continue
            if extraction.status == "empty":
                await store.mark_processed(publication.publication_id)
                continue
            await assign_publication(store, embedder, assigner, publication, extraction)

        state.last_analyze_at = now
        state.phase = "snapshot"
        await store.set_cycle_state(state)
        coverage = await _coverage_states(store, reader, source_ids, now)
        snapshot = await build_snapshot(
            store,
            now,
            coverage,
            collected_at=state.last_collect_at or now,
            analyzed_at=state.last_analyze_at or now,
        )
        await publish_snapshot(store, snapshot)
        state.phase = "idle"
        state.last_success_at = now
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
