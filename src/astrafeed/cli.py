"""Command line entry points for one-shot briefs and the combined HTTP/ingest service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta

import uvicorn
from openai import AsyncOpenAI
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from telethon import TelegramClient
from telethon.sessions import StringSession

from astrafeed.adapters.http.app import create_app
from astrafeed.adapters.llm.agenda import (
    OpenRouterAssigner,
    OpenRouterEmbedder,
    OpenRouterExtractor,
)
from astrafeed.adapters.llm.budgeted_client import BudgetedClient
from astrafeed.adapters.llm.openrouter import OpenRouterLLMClient
from astrafeed.adapters.llm.stub import StubLLMClient
from astrafeed.adapters.repository.sqlite.agenda import SqliteAgendaStore
from astrafeed.adapters.repository.sqlite.ingestion import SqliteIngestionStore
from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.repository.sqlite.pulse import SqliteCommentStore
from astrafeed.adapters.repository.sqlite.spend_budget import SqliteSpendBudget
from astrafeed.adapters.source.fake import FakeSource
from astrafeed.adapters.source.telegram import TelegramSource
from astrafeed.application.agenda_cycle import run_cycle
from astrafeed.application.agenda_query import (
    agenda_payload,
    health_payload,
    search_payload,
    story_payload,
)
from astrafeed.application.brief import build_brief
from astrafeed.application.ingestion import (
    IngestionCoordinator,
    IngestionLimits,
    limits_from_settings,
)
from astrafeed.application.pulse_ingest import CommentCollector
from astrafeed.config import Settings
from astrafeed.domain.agenda import EMBEDDING_MODEL, LOOKBACK
from astrafeed.logging_cfg import configure_logging

_log = logging.getLogger(__name__)


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


async def _storage(cfg: Settings):
    sqlite = cfg.database_url.startswith("sqlite+")
    engine = create_async_engine(
        cfg.database_url,
        connect_args={"timeout": 30} if sqlite else {},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if sqlite:
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
) -> None:
    collection_window = max(LOOKBACK, timedelta(hours=cfg.backfill_hours))
    reader = TelegramSource(client, backfill_window=collection_window)
    coordinator = IngestionCoordinator(
        posts, reader, resolver=reader, limits=limits_from_settings(cfg)
    )
    while True:
        await _ensure_connected(client)
        now = datetime.now(UTC)
        source_ids = await _resolve_union(coordinator, [*cfg.channels, *cfg.news_channels])

        async def collect(start: datetime, end: datetime, ids: list[int] = source_ids) -> None:
            if ids:
                result = await coordinator.ensure_window(ids, start, end)
                _log.info(
                    "agenda collect sources=%d incomplete=%d errors=%d",
                    len(ids),
                    sum(not coverage.complete for coverage in result.values()),
                    len(result.errors),
                )

        try:
            snapshot = await run_cycle(
                agenda,
                reader=posts,
                source_ids=source_ids,
                extractor=extractor,
                embedder=embedder,
                assigner=assigner,
                now=now,
                collect=collect,
                extract_concurrency=cfg.agenda.extract_concurrency,
                assign_concurrency=cfg.agenda.assign_concurrency,
                assignment_mode=cfg.agenda.assignment_mode,
                merge_cosine_threshold=cfg.agenda.merge_cosine_threshold,
                collection_window=collection_window,
            )
            if snapshot is None:
                _log.warning("agenda cycle did not publish (budget or incomplete)")
            else:
                _log.info(
                    "agenda snapshot %s stories=%d queue=%d",
                    snapshot.snapshot_id,
                    len(snapshot.agenda),
                    snapshot.queue_depth,
                )
        except OperationalError as exc:
            _log.error("agenda sqlite error: %s", str(exc.orig)[:160])
        except Exception as exc:
            _log.error("agenda cycle failed: %s", type(exc).__name__)
        await asyncio.sleep(cfg.poll_seconds)


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
    )


async def _serve(config_path: str) -> None:
    cfg = Settings.load(config_path)
    configure_logging("INFO", None)
    client = _telegram(cfg)
    await _ensure_connected(client)
    engine, session = await _storage(cfg)
    posts = SqliteIngestionStore(session)
    agenda = SqliteAgendaStore(session)
    await agenda.ensure_search()
    extractor, embedder, assigner = _agenda_llm(cfg, session)
    commit = git_commit()

    async def agenda_http(snapshot_id: str | None = None) -> dict:
        return await agenda_payload(agenda, snapshot_id=snapshot_id, now=datetime.now(UTC))

    async def search_http(
        q: str, snapshot_id: str | None = None, limit: int = 10, offset: int = 0
    ) -> dict:
        return await search_payload(
            agenda, q, snapshot_id=snapshot_id, now=datetime.now(UTC), limit=limit, offset=offset
        )

    async def story_http(story_id: str, snapshot_id: str | None = None) -> dict:
        return await story_payload(agenda, story_id, snapshot_id=snapshot_id, now=datetime.now(UTC))

    async def health_http() -> dict:
        return await health_payload(agenda, now=datetime.now(UTC), commit=commit)

    app = create_app(
        agenda=agenda_http,
        stories_search=search_http,
        story=story_http,
        health=health_http,
        info={"commit": commit},
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.api_host, port=cfg.api_port, log_config=None)
    )
    poll_task = asyncio.create_task(
        _agenda_poll(cfg, client, posts, agenda, extractor, embedder, assigner),
        name="agenda-cycle",
    )
    try:
        await server.serve()
    finally:
        poll_task.cancel()
        await asyncio.gather(poll_task, return_exceptions=True)
        await client.disconnect()
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
    if not refs:
        raise SystemExit("config.yaml has no channels: run scripts/channels.py --write")
    now = datetime.now(UTC)
    start = now - args.window
    client = _telegram(cfg)
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
        print(f"\n{'channel':<32} {'posts':>6}  status")
        total = 0
        for sid, ref in resolved.items():
            posts = len(await store.read_window(sid, start, now))
            total += posts
            status = "ok" if result[sid].complete else f"INCOMPLETE {result.errors.get(sid, '')}"
            print(f"{ref:<32} {posts:>6}  {status}")
        for ref, reason in failed.items():
            print(f"{ref:<32} {'-':>6}  UNRESOLVED {reason}")
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
