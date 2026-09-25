"""Command line entry points for one-shot briefs and the combined HTTP/ingest service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta

import httpx
import uvicorn
from openai import AsyncOpenAI
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from telethon import TelegramClient
from telethon.sessions import StringSession
from xpoz import AsyncXpozClient

from astrafeed.adapters.http.app import create_app
from astrafeed.adapters.http.okx_market import OkxMarket
from astrafeed.adapters.llm.agenda import (
    OpenRouterAssigner,
    OpenRouterDiscussionSummarizer,
    OpenRouterEmbedder,
    OpenRouterEvidenceVerifier,
    OpenRouterExtractor,
    OpenRouterTranslator,
)
from astrafeed.adapters.llm.budgeted_client import BudgetedClient
from astrafeed.adapters.llm.openrouter import OpenRouterLLMClient
from astrafeed.adapters.llm.stub import StubLLMClient
from astrafeed.adapters.repository.sqlite.agenda import (
    SqliteAgendaStore,
    drop_unused_search_index,
    migrate_agenda_index_tables,
)
from astrafeed.adapters.repository.sqlite.ingestion import SqliteIngestionStore, migrate_rss_sources
from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.repository.sqlite.pulse import SqliteCommentStore
from astrafeed.adapters.repository.sqlite.spend_budget import (
    SqliteSpendBudget,
    migrate_spend_reservations,
)
from astrafeed.adapters.repository.sqlite.xpoz import SqliteXpozThreads
from astrafeed.adapters.source.fake import FakeSource
from astrafeed.adapters.source.rss import RssReader
from astrafeed.adapters.source.telegram import TelegramSource
from astrafeed.adapters.source.xpoz import XpozReader
from astrafeed.application.agenda_cycle import run_cycle
from astrafeed.application.agenda_discussion import DiscussionEnricher
from astrafeed.application.agenda_localize import EnglishLocalizer
from astrafeed.application.agenda_query import (
    agenda_payload,
    health_payload,
    search_payload,
    story_payload,
)
from astrafeed.application.agenda_signals import add_price_moves
from astrafeed.application.brief import build_brief
from astrafeed.application.ingestion import (
    IngestionCoordinator,
    IngestionLimits,
    limits_from_settings,
)
from astrafeed.application.pulse_ingest import CommentCollector
from astrafeed.application.reddit_ingest import collect_reddit_feeds, resolve_reddit_feeds
from astrafeed.application.rss_ingest import collect_feeds, resolve_feeds
from astrafeed.application.xpoz_discussion import CompositeComments, XpozComments
from astrafeed.application.xpoz_ingest import (
    collect_xpoz_accounts,
    collect_xpoz_search,
    resolve_xpoz_accounts,
    resolve_xpoz_search,
)
from astrafeed.config import Settings
from astrafeed.domain.agenda import EMBEDDING_MODEL, LOOKBACK, Snapshot
from astrafeed.logging_cfg import configure_logging

_log = logging.getLogger(__name__)


async def _refresh_displayed_posts(snapshot, posts, reader: TelegramSource) -> int:
    """Reread the published top's source IDs without scanning channel history."""
    by_source: dict[int, set[int]] = {}
    for card in snapshot.agenda:
        detail = snapshot.stories.get(card.story_id)
        if detail is None:
            continue
        for pub in detail.publications:
            source, _, external = pub.publication_id.partition(":")
            if source.isdecimal() and external.isdecimal():
                by_source.setdefault(int(source), set()).add(int(external))

    semaphore = asyncio.Semaphore(4)

    async def refresh(source_id: int, ids: set[int]) -> int:
        async with semaphore:
            try:
                source = await posts.get_source(source_id)
                if source is None or source.telegram_id is None or source.telegram_id < 0:
                    return 0
                items = await reader.read_posts(source.telegram_id, sorted(ids))
                if items:
                    await posts.store_items(source_id, items)
                return len(items)
            except Exception as exc:
                _log.warning(
                    "agenda source refresh failed source=%d error=%s",
                    source_id,
                    type(exc).__name__,
                )
                return 0

    counts = await asyncio.gather(
        *(refresh(source_id, ids) for source_id, ids in by_source.items())
    )
    return sum(counts)


def git_commit() -> str:
    if os.environ.get("GIT_COMMIT"):
        return os.environ["GIT_COMMIT"]
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=os.path.dirname(__file__),
            )
            .decode()
            .strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _window(value: str) -> timedelta:
    match = re.fullmatch(r"(\d+)([hd])", value.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError("window must be expressed as hours (24h) or days (1d)")
    amount, unit = int(match.group(1)), match.group(2)
    if amount <= 0:
        raise argparse.ArgumentTypeError("window must be positive")
    return timedelta(hours=amount if unit == "h" else amount * 24)


def _create_missing_indexes(sync_connection) -> None:
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(sync_connection, checkfirst=True)


async def _storage(cfg: Settings):
    sqlite = cfg.database_url.startswith("sqlite+")
    engine = create_async_engine(
        cfg.database_url,
        connect_args={"timeout": 30} if sqlite else {},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if sqlite:
            await migrate_rss_sources(conn)
            await migrate_spend_reservations(conn)
            await migrate_agenda_index_tables(conn)
            await drop_unused_search_index(conn)
            # create_all skips indexes of tables that already exist.
            await conn.run_sync(_create_missing_indexes)
    if sqlite:
        # Separate connection: SQLite refuses to change the journal mode inside
        # a transaction that has already written (the migrations above may).
        async with engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _llm(cfg: Settings, session, *, stub: bool = False):
    if stub:
        return StubLLMClient()
    budget = SqliteSpendBudget(session, daily_limit=cfg.llm_daily_budget_usd)
    openai = AsyncOpenAI(api_key=cfg.openrouter.api_key, base_url=cfg.openrouter.base_url)
    client = BudgetedClient(
        openai,
        store=budget,
        user_id=0,
        reservation_amount=cfg.llm_reservation_usd,
        max_tokens=cfg.llm_max_tokens,
    )
    return OpenRouterLLMClient(
        client=client,
        model=cfg.openrouter.cheap_model,
        strong_model=cfg.openrouter.strong_model,
        score_parse_retries=cfg.openrouter.score_parse_retries,
        score_max_items_per_batch=cfg.openrouter.score_max_items_per_batch,
        score_coverage_retries=cfg.openrouter.score_coverage_retries,
        score_token_limit_param=cfg.openrouter.score_token_limit_param,
        score_max_tokens=cfg.openrouter.score_max_tokens,
    )


def _telegram(cfg: Settings) -> TelegramClient:
    if not cfg.telegram.session:
        raise RuntimeError("TELEGRAM_SESSION is required for live ingestion")
    return TelegramClient(
        StringSession(cfg.telegram.session),
        cfg.telegram.api_id,
        cfg.telegram.api_hash,
        connection_retries=-1,
    )


async def _ensure_connected(client: TelegramClient) -> None:
    while not client.is_connected():
        try:
            await client.connect()
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("Telegram connection failed; retrying in 5 seconds")
            await asyncio.sleep(5)


async def _brief(args: argparse.Namespace) -> None:
    cfg = Settings.load(args.config)
    configure_logging("INFO", None)
    now = datetime.now(UTC)
    interests = [token.strip().upper() for token in args.tokens.split(",") if token.strip()]
    if args.stub_llm:
        result = await build_brief(
            FakeSource([]),
            StubLLMClient(),
            cfg.channels,
            args.window,
            now,
            interests=interests,
            language=cfg.language,
        )
    else:
        client = _telegram(cfg)
        await _ensure_connected(client)
        engine, session = await _storage(cfg)
        try:
            store = SqliteIngestionStore(session)
            reader = TelegramSource(client, backfill_window=args.window)
            result = await build_brief(
                store,
                _llm(cfg, session),
                cfg.channels,
                args.window,
                now,
                reader=reader,
                resolver=reader,
                interests=interests,
                limits=limits_from_settings(cfg),
                language=cfg.language,
            )
        finally:
            await client.disconnect()
            await engine.dispose()
    print(result.markdown)


def brief() -> None:
    parser = argparse.ArgumentParser(prog="astrafeed-brief", description="Build a token brief")
    parser.add_argument(
        "--tokens", required=True, help="Comma-separated tokens, for example SOL,OKB"
    )
    parser.add_argument("--window", type=_window, default=timedelta(hours=24))
    parser.add_argument(
        "--stub-llm", action="store_true", help="Run offline without Telegram or model keys"
    )
    parser.add_argument("--config", default="config.yaml")
    asyncio.run(_brief(parser.parse_args()))


async def _resolve_union(coordinator: IngestionCoordinator, refs: list[str]) -> list[int]:
    seen: dict[int, int] = {}
    for ref in dict.fromkeys(refs):
        try:
            source = await coordinator.resolve_public_ref(ref)
        except Exception:
            _log.exception("Could not resolve configured source %s", ref)
            continue
        if source.telegram_id is not None:
            seen.setdefault(source.telegram_id, source.id)
    return list(seen.values())


async def _agenda_poll(
    cfg: Settings,
    client: TelegramClient,
    posts: SqliteIngestionStore,
    agenda: SqliteAgendaStore,
    extractor: OpenRouterExtractor,
    embedder: OpenRouterEmbedder,
    assigner: OpenRouterAssigner,
    evidence_verifier: OpenRouterEvidenceVerifier,
    summarizer: OpenRouterDiscussionSummarizer,
    translator: OpenRouterTranslator,
    xpoz_reader: XpozReader | None = None,
    xpoz_threads: SqliteXpozThreads | None = None,
) -> None:
    collection_window = max(LOOKBACK, timedelta(hours=cfg.backfill_hours))
    reader = TelegramSource(client, backfill_window=collection_window)
    # Most discussion groups are readable only by members, so the account may
    # join a few per cycle (agenda.discussion_joins_per_cycle).
    comment_source = TelegramSource(
        client, discussion_join_limit_per_run=cfg.agenda.discussion_joins_per_cycle
    )
    discussion_reader = (
        CompositeComments(comment_source, XpozComments(xpoz_reader, xpoz_threads))
        if xpoz_reader is not None and xpoz_threads is not None
        else comment_source
    )
    discussions = DiscussionEnricher(discussion_reader, summarizer)
    english = EnglishLocalizer(translator)
    market = OkxMarket()

    async def discuss_in_english(snapshot: Snapshot, now: datetime) -> Snapshot:
        comment_source.reset_discussion_join_budget()
        # Translate after comments are attached so their quotes are covered too.
        snapshot = await english.localize(await discussions.enrich(snapshot, now))
        return await add_price_moves(snapshot, market, now)

    coordinator = IngestionCoordinator(
        posts, reader, resolver=reader, limits=limits_from_settings(cfg)
    )
    source_ids: list[int] = []
    rss_feeds: dict[int, str] = {}
    reddit_feeds: dict[int, str] = {}
    xpoz_accounts: dict[int, str] = {}
    xpoz_search_id: int | None = None
    while True:
        now = datetime.now(UTC)
        cycle_state = await agenda.get_cycle_state()
        collect_due = (
            cycle_state.last_collect_at is None
            or now - cycle_state.last_collect_at >= timedelta(seconds=cfg.poll_seconds)
        )
        if collect_due or not source_ids:
            source_ids = []
            if cfg.channels or cfg.news_channels:
                try:
                    # Resolving 38 channels checks both identity and read access
                    # sequentially. A cold Telegram session can take longer than
                    # ten seconds even when every source is available.
                    async with asyncio.timeout(120):
                        await _ensure_connected(client)
                        source_ids = await _resolve_union(
                            coordinator, [*cfg.channels, *cfg.news_channels]
                        )
                except Exception as exc:
                    _log.warning("agenda Telegram source resolution failed: %s", type(exc).__name__)
            try:
                rss_feeds = await resolve_feeds(posts, cfg.rss_feeds)
                source_ids.extend(rss_feeds)
            except Exception as exc:
                _log.error("agenda RSS source resolution failed: %s", type(exc).__name__)
                rss_feeds = {}
            try:
                reddit_feeds = await resolve_reddit_feeds(posts, cfg.reddit_feeds)
                source_ids.extend(reddit_feeds)
            except Exception as exc:
                _log.error("agenda Reddit source resolution failed: %s", type(exc).__name__)
                reddit_feeds = {}
            if cfg.xpoz_accounts:
                try:
                    xpoz_accounts = await resolve_xpoz_accounts(posts, cfg.xpoz_accounts)
                    source_ids.extend(xpoz_accounts)
                    xpoz_search_id = await resolve_xpoz_search(posts)
                    source_ids.append(xpoz_search_id)
                except Exception as exc:
                    _log.error("agenda Xpoz source resolution failed: %s", type(exc).__name__)
                    xpoz_accounts = {}
                    xpoz_search_id = None
            if not source_ids:
                cycle_state.last_error = "source_unavailable"
                cycle_state.phase = "idle"
                await agenda.set_cycle_state(cycle_state)
                await asyncio.sleep(cfg.poll_seconds)
                continue

        async def collect(
            start: datetime,
            end: datetime,
            ids: list[int] = source_ids,
            feeds: dict[int, str] = rss_feeds,
            subreddits: dict[int, str] = reddit_feeds,
            x_accounts: dict[int, str] = xpoz_accounts,
            x_search_id: int | None = xpoz_search_id,
        ) -> None:
            if ids:
                telegram_ids = [
                    sid
                    for sid in ids
                    if sid not in feeds
                    and sid not in subreddits
                    and sid not in x_accounts
                    and sid != x_search_id
                ]
                result = await coordinator.ensure_window(telegram_ids, start, end)
                async with httpx.AsyncClient(
                    timeout=15,
                    follow_redirects=True,
                    headers={"User-Agent": "AstraFeed/0.1 RSS reader"},
                ) as http:
                    rss_errors = await collect_feeds(posts, RssReader(http), feeds, start, end)
                    reddit_errors = await collect_reddit_feeds(
                        posts, RssReader(http), subreddits, start, end
                    )
                xpoz_errors: dict[int, str] = {}
                if xpoz_reader is not None and x_search_id is not None:
                    search_error = await collect_xpoz_search(
                        posts,
                        xpoz_reader,
                        x_search_id,
                        x_accounts,
                        start,
                        end,
                        threads=xpoz_threads,
                    )
                    if search_error:
                        xpoz_errors[x_search_id] = search_error
                    xpoz_errors.update(
                        await collect_xpoz_accounts(
                            posts, xpoz_reader, x_accounts, start, end, threads=xpoz_threads
                        )
                    )
                _log.info(
                    "agenda collect sources=%d incomplete=%d errors=%d",
                    len(ids),
                    sum(not coverage.complete for coverage in result.values())
                    + len(rss_errors)
                    + len(reddit_errors)
                    + len(xpoz_errors),
                    len(result.errors) + len(rss_errors) + len(reddit_errors) + len(xpoz_errors),
                )
                previous_snapshot = await agenda.get_snapshot(None)
                if previous_snapshot is not None:
                    refreshed = await _refresh_displayed_posts(previous_snapshot, posts, reader)
                    _log.info("agenda refreshed displayed posts=%d", refreshed)

        snapshot = None
        try:
            snapshot = await run_cycle(
                agenda,
                reader=posts,
                source_ids=source_ids,
                extractor=extractor,
                embedder=embedder,
                assigner=assigner,
                evidence_verifier=evidence_verifier,
                now=now,
                collect=collect if collect_due else None,
                ingest=collect_due,
                extract_concurrency=cfg.agenda.extract_concurrency,
                assign_concurrency=cfg.agenda.assign_concurrency,
                backfill_batch_size=cfg.agenda.backfill_batch_size,
                assignment_mode=cfg.agenda.assignment_mode,
                merge_cosine_threshold=cfg.agenda.merge_cosine_threshold,
                collection_window=collection_window,
                max_posts_per_cycle=cfg.agenda.cycle_post_limit,
                discuss=discuss_in_english,
            )
            if snapshot is None:
                _log.warning("agenda cycle did not publish (budget or incomplete)")
            else:
                _log.info(
                    "agenda batch %s stories=%d queue=%d processing=%s",
                    snapshot.snapshot_id,
                    len(snapshot.agenda),
                    snapshot.queue_depth,
                    "processing_in_progress" in snapshot.limitations,
                )
        except OperationalError as exc:
            _log.error("agenda sqlite error: %s", str(exc.orig)[:160])
        except Exception as exc:
            _log.error("agenda cycle failed: %s", type(exc).__name__)
        if snapshot is not None and "processing_in_progress" in snapshot.limitations:
            await asyncio.sleep(0)
        else:
            latest_collect = (await agenda.get_cycle_state()).last_collect_at
            remaining = (
                cfg.poll_seconds
                if latest_collect is None
                else (
                    latest_collect + timedelta(seconds=cfg.poll_seconds) - datetime.now(UTC)
                ).total_seconds()
            )
            await asyncio.sleep(max(1, remaining))


def _agenda_llm(cfg: Settings, session):
    budget = SqliteSpendBudget(session, daily_limit=cfg.llm_daily_budget_usd)
    openai = AsyncOpenAI(api_key=cfg.openrouter.api_key, base_url=cfg.openrouter.base_url)
    client = BudgetedClient(
        openai,
        store=budget,
        user_id=0,
        reservation_amount=cfg.llm_reservation_usd,
        max_tokens=cfg.llm_max_tokens,
    )
    model = cfg.openrouter.cheap_model
    return (
        OpenRouterExtractor(client, model),
        OpenRouterEmbedder(client, cfg.openrouter.embedding_model or EMBEDDING_MODEL),
        OpenRouterAssigner(client, model),
        OpenRouterEvidenceVerifier(client, model),
        OpenRouterDiscussionSummarizer(client, model),
        OpenRouterTranslator(client, model),
    )


async def _serve(config_path: str) -> None:
    cfg = Settings.load(config_path)
    configure_logging("INFO", None)
    client = _telegram(cfg)
    engine, session = await _storage(cfg)
    posts = SqliteIngestionStore(session)
    agenda = SqliteAgendaStore(session)
    xpoz_threads = SqliteXpozThreads(session)
    xpoz_client: AsyncXpozClient | None = None
    xpoz_reader: XpozReader | None = None
    if cfg.xpoz_accounts and os.environ.get("XPOZ_API_KEY"):
        try:
            xpoz_client = AsyncXpozClient(
                api_key=os.environ["XPOZ_API_KEY"], check_update=False, timeout=30
            )
            xpoz_reader = XpozReader(xpoz_client)
            _log.info("Xpoz source enabled for %d configured accounts", len(cfg.xpoz_accounts))
        except Exception as exc:
            _log.error("Xpoz setup unavailable: %s", type(exc).__name__)
            if xpoz_client is not None:
                await xpoz_client.close()
            xpoz_client = None
    extractor, embedder, assigner, evidence_verifier, summarizer, translator = _agenda_llm(
        cfg, session
    )
    commit = git_commit()

    async def agenda_http(
        snapshot_id: str | None = None, since_snapshot_id: str | None = None
    ) -> dict:
        return await agenda_payload(
            agenda,
            snapshot_id=snapshot_id,
            since_snapshot_id=since_snapshot_id,
            now=datetime.now(UTC),
        )

    async def search_http(
        q: str, snapshot_id: str | None = None, limit: int = 10, offset: int = 0
    ) -> dict:
        return await search_payload(
            agenda, q, snapshot_id=snapshot_id, now=datetime.now(UTC), limit=limit, offset=offset
        )

    async def story_http(story_id: str, snapshot_id: str | None = None) -> dict:
        return await story_payload(agenda, story_id, snapshot_id=snapshot_id, now=datetime.now(UTC))

    async def health_http() -> dict:
        payload = await health_payload(agenda, now=datetime.now(UTC), commit=commit)
        payload["spend"] = await SqliteSpendBudget(session).summary()
        return payload

    app = create_app(
        agenda=agenda_http,
        stories_search=search_http,
        story=story_http,
        health=health_http,
        info={"commit": commit},
        rss_feeds=cfg.rss_feeds,
        reddit_feeds=cfg.reddit_feeds,
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.api_host, port=cfg.api_port, log_config=None)
    )
    poll_task = asyncio.create_task(
        _agenda_poll(
            cfg,
            client,
            posts,
            agenda,
            extractor,
            embedder,
            assigner,
            evidence_verifier,
            summarizer,
            translator,
            xpoz_reader,
            xpoz_threads,
        ),
        name="agenda-cycle",
    )
    try:
        await server.serve()
    finally:
        poll_task.cancel()
        await asyncio.gather(poll_task, return_exceptions=True)
        await client.disconnect()
        if xpoz_client is not None:
            await xpoz_client.close()
        await engine.dispose()


def serve() -> None:
    parser = argparse.ArgumentParser(prog="astrafeed-serve")
    parser.add_argument("--config", default="config.yaml")
    asyncio.run(_serve(parser.parse_args().config))


async def _backfill_posts(args: argparse.Namespace) -> None:
    """Read every configured channel over the whole window and report per-channel counts.

    Limits are raised well above the polling defaults: a multi-day backfill of an
    active channel easily exceeds 200 posts, and a capped read would leave the
    window incomplete. Safe to re-run: covered intervals are skipped.
    """
    cfg = Settings.load(args.config)
    configure_logging("INFO", None)
    refs = list(dict.fromkeys([*cfg.channels, *cfg.news_channels]))
    if not refs and not cfg.rss_feeds and not cfg.reddit_feeds:
        raise SystemExit("config.yaml has no channels, rss_feeds or reddit_feeds")
    now = datetime.now(UTC)
    start = now - args.window
    client = _telegram(cfg)
    if refs:
        await _ensure_connected(client)
    engine, session = await _storage(cfg)
    try:
        store = SqliteIngestionStore(session)
        reader = TelegramSource(client, backfill_window=args.window)
        coordinator = IngestionCoordinator(
            store,
            reader,
            resolver=reader,
            limits=IngestionLimits(
                max_channels_first_run=cfg.ingestion_max_channels_first_run,
                max_posts_per_channel=args.max_posts,
                max_posts_per_run=args.max_posts * len(refs),
            ),
        )
        resolved: dict[int, str] = {}
        failed: dict[str, str] = {}
        for ref in refs:
            try:
                resolved[(await coordinator.resolve_public_ref(ref)).id] = ref
            except Exception as e:  # noqa: BLE001 - report every bad ref, keep going
                failed[ref] = str(e)
        result = await coordinator.ensure_window(list(resolved), start, now)
        rss_feeds = await resolve_feeds(store, cfg.rss_feeds)
        reddit_feeds = await resolve_reddit_feeds(store, cfg.reddit_feeds)
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "AstraFeed/0.1 RSS reader"},
        ) as http:
            rss_errors = await collect_feeds(store, RssReader(http), rss_feeds, start, now)
            reddit_errors = await collect_reddit_feeds(
                store, RssReader(http), reddit_feeds, start, now
            )
        print(f"\n{'channel':<32} {'posts':>6}  status")
        total = 0
        for sid, ref in resolved.items():
            posts = await store.count_window(sid, start, now)
            total += posts
            status = "ok" if result[sid].complete else f"INCOMPLETE {result.errors.get(sid, '')}"
            print(f"{ref:<32} {posts:>6}  {status}")
        for ref, reason in failed.items():
            print(f"{ref:<32} {'-':>6}  UNRESOLVED {reason}")
        for sid, url in rss_feeds.items():
            articles = await store.count_window(sid, start, now)
            total += articles
            status = "ok" if sid not in rss_errors else f"INCOMPLETE {rss_errors[sid]}"
            print(f"{url:<32} {articles:>6}  {status}")
        for sid, subreddit in reddit_feeds.items():
            posts = await store.count_window(sid, start, now)
            total += posts
            status = "ok" if sid not in reddit_errors else f"INCOMPLETE {reddit_errors[sid]}"
            print(f"{'r/' + subreddit:<32} {posts:>6}  {status}")
        print(f"\nTotal posts in [{start:%Y-%m-%d %H:%M}, {now:%Y-%m-%d %H:%M}] UTC: {total}")
    finally:
        await client.disconnect()
        await engine.dispose()


async def _backfill_comments(args: argparse.Namespace) -> None:
    """Read discussion threads of stored posts in the window; safe to re-run.

    Posts must be downloaded first (backfill-posts): the collector walks the
    raw cache, so a missing post means its thread is never read.
    """
    cfg = Settings.load(args.config)
    configure_logging("INFO", None)
    if not cfg.channels:
        raise SystemExit("config.yaml has no channels: run scripts/channels.py --write")
    now = datetime.now(UTC)
    start = now - args.window
    client = _telegram(cfg)
    await _ensure_connected(client)
    engine, session = await _storage(cfg)
    try:
        posts = SqliteIngestionStore(session)
        comments = SqliteCommentStore(session)
        # Reading never needs a join: every configured discussion is readable as is.
        reader = TelegramSource(client, discussion_join_limit_per_run=0)
        sources: list[tuple[int, str]] = []
        for ref in cfg.channels:
            try:
                telegram_id = await reader.resolve_public_ref(ref)
                sources.append(((await posts.upsert_source(telegram_id)).id, ref))
            except Exception as e:  # noqa: BLE001 - report every bad ref, keep going
                print(f"{ref:<28} UNRESOLVED {e}")
        reports = await CommentCollector(posts, comments, reader).collect(sources, start, now)
        head = f"{'channel':<28} {'posts':>5} {'w/cmt':>5} {'read':>5} {'skip':>5}"
        print(f"\n{head} {'fail':>4} {'trunc':>5} {'comments':>8}  status")
        for r in reports:
            status = f"ERROR {r.error}" if r.error else "ok"
            print(
                f"{r.ref:<28} {r.posts:>5} {r.with_comments:>5} {r.scanned:>5} {r.skipped:>5}"
                f" {r.failed:>4} {r.truncated:>5} {r.comments:>8}  {status}"
            )
        total = sum(r.comments for r in reports)
        span = f"[{start:%Y-%m-%d %H:%M}, {now:%Y-%m-%d %H:%M}] UTC"
        print(f"\nComments on posts from {span}: {total}")
    finally:
        await client.disconnect()
        await engine.dispose()


def pulse() -> None:
    parser = argparse.ArgumentParser(prog="astrafeed-pulse", description="Community Pulse")
    parser.add_argument("--config", default="config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    posts = sub.add_parser("backfill-posts", help="Download channel posts for the window")
    posts.add_argument("--window", type=_window, default=timedelta(days=8))
    posts.add_argument("--max-posts", type=int, default=3000, help="Per-channel post cap")
    comments = sub.add_parser("backfill-comments", help="Read comment threads of stored posts")
    comments.add_argument("--window", type=_window, default=timedelta(hours=48))
    args = parser.parse_args()
    if args.command == "backfill-posts":
        asyncio.run(_backfill_posts(args))
    elif args.command == "backfill-comments":
        asyncio.run(_backfill_comments(args))
