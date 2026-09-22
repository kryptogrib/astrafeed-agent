"""Command line entry points for one-shot briefs and the combined HTTP/ingest service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta

import uvicorn
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from telethon import TelegramClient
from telethon.sessions import StringSession

from astrafeed.adapters.http.app import create_app
from astrafeed.adapters.llm.budgeted_client import BudgetedClient
from astrafeed.adapters.llm.openrouter import OpenRouterLLMClient
from astrafeed.adapters.llm.stub import StubLLMClient
from astrafeed.adapters.repository.sqlite.ingestion import SqliteIngestionStore
from astrafeed.adapters.repository.sqlite.models import Base
from astrafeed.adapters.repository.sqlite.spend_budget import SqliteSpendBudget
from astrafeed.adapters.source.fake import FakeSource
from astrafeed.adapters.source.telegram import TelegramSource
from astrafeed.application.brief import build_brief
from astrafeed.application.ingestion import IngestionCoordinator, limits_from_settings
from astrafeed.config import Settings
from astrafeed.logging_cfg import configure_logging

_log = logging.getLogger(__name__)


def _window(value: str) -> timedelta:
    match = re.fullmatch(r"(\d+)([hd])", value.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError("window must be expressed as hours (24h) or days (1d)")
    amount, unit = int(match.group(1)), match.group(2)
    if amount <= 0:
        raise argparse.ArgumentTypeError("window must be positive")
    return timedelta(hours=amount if unit == "h" else amount * 24)


async def _storage(cfg: Settings):
    engine = create_async_engine(cfg.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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


async def _poll(cfg: Settings, client: TelegramClient, store: SqliteIngestionStore) -> None:
    reader = TelegramSource(client, backfill_window=timedelta(hours=cfg.backfill_hours))
    coordinator = IngestionCoordinator(
        store, reader, resolver=reader, limits=limits_from_settings(cfg)
    )
    while True:
        await _ensure_connected(client)
        now = datetime.now(UTC)
        ids = []
        for channel in cfg.channels:
            try:
                ids.append((await coordinator.resolve_public_ref(channel)).id)
            except Exception:
                _log.exception("Could not resolve configured source %s", channel)
        if ids:
            result = await coordinator.ensure_window(
                ids, now - timedelta(hours=cfg.backfill_hours), now
            )
            _log.info(
                "ingest tick sources=%d incomplete=%d errors=%d",
                len(ids),
                sum(not c.complete for c in result.values()),
                len(result.errors),
            )
        await asyncio.sleep(cfg.poll_seconds)


async def _serve(config_path: str) -> None:
    cfg = Settings.load(config_path)
    configure_logging("INFO", None)
    client = _telegram(cfg)
    await _ensure_connected(client)
    engine, session = await _storage(cfg)
    store = SqliteIngestionStore(session)
    app = create_app()
    server = uvicorn.Server(
        uvicorn.Config(app, host=cfg.api_host, port=cfg.api_port, log_config=None)
    )
    poll_task = asyncio.create_task(_poll(cfg, client, store), name="ingest-poll")
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
