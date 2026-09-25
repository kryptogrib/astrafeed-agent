from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from astrafeed.adapters.repository.sqlite.ingestion import SqliteIngestionStore
from astrafeed.adapters.repository.sqlite.models import Base, CommentRow
from astrafeed.adapters.repository.sqlite.pulse import SqliteCommentStore
from astrafeed.application.pulse_ingest import CommentCollector
from astrafeed.domain.models import CommentFetch, CommentStatus, DiscussionComment, Item
from astrafeed.domain.pulse import StoredComment, ThreadState

T0 = datetime(2026, 9, 20, 12, tzinfo=UTC)
REF = "@chan"
PEER = "channel:777"


def _post(pid: str, hours_ago: int = 1) -> Item:
    return Item(
        channel_ref=REF,
        external_id=pid,
        text="post",
        link=f"https://t.me/chan/{pid}",
        timestamp=T0 - timedelta(hours=hours_ago),
    )


def _comment(cid: int, reply_to: str | None = "1000") -> DiscussionComment:
    return DiscussionComment(
        external_id=str(cid),
        text=f"comment {cid}",
        timestamp=T0 + timedelta(minutes=cid % 60),
        reply_to_id=reply_to,
        peer_id=PEER,
    )


class FakeThreads:
    """Reply counters and thread contents per post id, plus a call log."""

    def __init__(self) -> None:
        self.threads: dict[str, list[DiscussionComment]] = {}
        self.fail: dict[str, CommentStatus] = {}
        self.fetched: list[str] = []

    async def reply_counts(self, channel_ref: str, post_ids: Sequence[str]) -> dict[str, int]:
        return {p: len(self.threads[p]) for p in post_ids if p in self.threads}

    async def fetch_comments_detailed(self, item: Item, *, limit: int, parent_limit: int = 0):
        self.fetched.append(item.external_id)
        if item.external_id in self.fail:
            return CommentFetch(status=self.fail[item.external_id], reason="boom")
        comments = self.threads[item.external_id][:limit]
        return CommentFetch(
            status=CommentStatus.FETCHED if comments else CommentStatus.EMPTY,
            comments=tuple(comments),
            raw_count=len(comments),
            limit=limit,
            possibly_truncated=len(self.threads[item.external_id]) >= limit,
            discussion_peer_id=PEER,
            root_id="1000",
        )


@pytest.fixture
async def env(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'pulse.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)
    posts, comments = SqliteIngestionStore(session), SqliteCommentStore(session)
    source = await posts.upsert_source(42)
    await posts.store_items(source.id, [_post("10"), _post("11"), _post("12")])
    reader = FakeThreads()
    reader.threads = {"10": [_comment(1), _comment(2, reply_to="1")], "11": []}
    yield source.id, posts, comments, reader
    await engine.dispose()


async def _run(env, limit: int = 100):
    sid, posts, comments, reader = env
    collector = CommentCollector(posts, comments, reader, now=lambda: T0, thread_limit=limit)
    return (await collector.collect([(sid, REF)], T0 - timedelta(days=2), T0))[0]


async def _stored(env):
    sid, _, comments, _ = env
    return await comments.read_comments(sid, T0 - timedelta(days=2), T0 + timedelta(days=1))


async def test_stores_comment_fields_and_skips_posts_without_comments(env):
    report = await _run(env)
    rows = await _stored(env)
    assert env[3].fetched == ["10"]  # 11 has counter 0, 12 has no discussion
    assert report.posts == 3 and report.with_comments == 1 and report.comments == 2
    by_id = {r.comment_id: r for r in rows}
    assert by_id["1"].comment_key == f"{PEER}:1"
    assert by_id["1"].parent_comment_id is None  # answers the post (thread root)
    assert by_id["2"].parent_comment_id == "1"
    assert by_id["2"].link == "https://t.me/chan/10?comment=2"
    states = await env[2].thread_states(env[0], ["10", "11", "12"])
    assert states["11"].status is CommentStatus.EMPTY
    assert states["12"].status is CommentStatus.UNAVAILABLE


async def test_rerun_is_idempotent_and_skips_unchanged_threads(env):
    await _run(env)
    report = await _run(env)
    assert env[3].fetched == ["10"]
    assert report.scanned == 0 and report.comments == 2
    assert len(await _stored(env)) == 2


async def test_late_comment_on_old_post_is_picked_up(env):
    await _run(env)
    env[3].threads["10"].append(_comment(3))
    env[3].threads["11"].append(_comment(4))
    report = await _run(env)
    assert sorted(env[3].fetched) == ["10", "10", "11"]
    assert {r.comment_id for r in await _stored(env)} == {"1", "2", "3", "4"}
    assert report.comments == 4


async def test_flood_wait_is_not_recorded_as_empty_and_is_retried(env):
    env[3].fail["10"] = CommentStatus.FLOOD_WAIT
    report = await _run(env)
    state = (await env[2].thread_states(env[0], ["10"]))["10"]
    assert state.status is CommentStatus.FLOOD_WAIT and state.reply_counter is None
    assert report.failed == 1 and "flood wait" in report.error
    del env[3].fail["10"]
    await _run(env)
    assert env[3].fetched == ["10", "10"]
    assert len(await _stored(env)) == 2


async def test_truncated_thread_is_rescanned(env):
    await _run(env, limit=2)  # thread has exactly 2 -> reader flags possibly_truncated
    await _run(env, limit=2)
    assert env[3].fetched == ["10", "10"]
    await _run(env, limit=100)
    await _run(env, limit=100)
    assert env[3].fetched == ["10", "10", "10"]


async def test_thread_states_reads_only_requested_posts_across_large_windows(env):
    sid, _, comments, _ = env
    await comments.save_thread(ThreadState(sid, "historical", CommentStatus.FETCHED, 1, 1, T0), ())
    await comments.save_thread(ThreadState(sid, "10", CommentStatus.EMPTY, 0, 0, T0), ())

    states = await comments.thread_states(sid, [*(str(i) for i in range(1200)), "10"])

    assert list(states) == ["10"]


async def test_save_thread_batches_comments_and_reclassifies_only_edited_text(env):
    sid, _, comments, _ = env
    state = ThreadState(sid, "10", CommentStatus.FETCHED, 1200, 1200, T0)
    rows = [
        StoredComment(
            f"{PEER}:{i}",
            sid,
            "10",
            str(i),
            T0,
            f"comment {i}",
            f"https://t.me/chan/10?comment={i}",
        )
        for i in range(1200)
    ]
    statements = []
    engine = comments._session.kw["bind"]

    def count_comment_writes(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("INSERT INTO comment "):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count_comment_writes)
    try:
        await comments.save_thread(state, rows)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_comment_writes)
    assert len(statements) <= 10

    async with comments._session() as session, session.begin():
        await session.execute(
            update(CommentRow).where(CommentRow.source_id == sid).values(classified=True)
        )

    edited = [
        StoredComment(**{**row.__dict__, "text": "revised"}) if row.comment_id == "1" else row
        for row in rows
    ]
    await comments.save_thread(state, edited)
    async with comments._session() as session:
        stored = (
            await session.scalars(select(CommentRow).where(CommentRow.comment_id.in_(["1", "2"])))
        ).all()
    by_id = {row.comment_id: row for row in stored}
    assert by_id["1"].text == "revised" and by_id["1"].classified is False
    assert by_id["2"].classified is True
