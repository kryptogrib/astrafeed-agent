from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.application.agenda_snapshot import build_snapshot
from astrafeed.domain.agenda import PublicationVersion, text_hash


@pytest.mark.asyncio
async def test_coverage_counts_stopped_queue_entries_as_failed_not_as_queued_only():
    store = InMemoryAgendaStore()
    now = datetime(2026, 9, 25, 12, tzinfo=UTC)
    for name, reason in (("stopped", "extract_error:3"), ("retryable", "assign_error:1")):
        when = now - timedelta(hours=1)
        await store.record_publication(
            PublicationVersion(
                name, 1, name, name, text_hash(name), when, now, "@a", f"https://t.me/a/{name}"
            )
        )
        await store.enqueue(name, reason)

    snapshot = await build_snapshot(
        store,
        now,
        {1: {"current_complete": True, "previous_complete": True, "processed": True}},
        collected_at=now,
        analyzed_at=now,
    )

    assert snapshot.coverage.publications_failed == 1
    assert snapshot.coverage.publications_queued == 2
