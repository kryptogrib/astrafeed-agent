"""One-shot engine-to-brief composition seam."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from typing import Any

from astrafeed.adapters.repository.memory import InMemoryRepository
from astrafeed.adapters.source.window import WindowSource
from astrafeed.application.ingestion import IngestionCoordinator, IngestionLimits
from astrafeed.domain import Channel, Interest
from astrafeed.pipeline import Pipeline
from astrafeed.ports.llm import LLMClient
from astrafeed.ports.source import PublicRefResolver, WindowReader
from astrafeed.ports.source import Source as FeedSource
from astrafeed.prefilter.filters import PrefilterConfig
from astrafeed.report.service import ReportService


@dataclass(frozen=True)
class BriefCoverage:
    complete: bool
    truncated: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class BriefResult:
    markdown: str
    coverage: BriefCoverage


_LINK_RE = re.compile(r'<a href="([^"]+)">(.*?)</a>', re.DOTALL)
_TAG_RE = re.compile(r"</?(?:b|i|u|code)>")


def _markdown(text: str) -> str:
    text = _LINK_RE.sub(
        lambda match: f"[{unescape(match.group(2))}]({unescape(match.group(1))})", text
    )
    text = text.replace("<b>", "**").replace("</b>", "**")
    text = text.replace("<i>", "*").replace("</i>", "*")
    text = text.replace("<code>", "`").replace("</code>", "`")
    text = _TAG_RE.sub("", text)
    return unescape(text)


async def build_brief(
    store: Any,
    llm: LLMClient,
    tokens: list[str] | tuple[str, ...],
    window: timedelta,
    now: datetime,
    *,
    reader: WindowReader | None = None,
    resolver: PublicRefResolver | None = None,
    interests: list[str] | None = None,
    limits: IngestionLimits | None = None,
    language: str = "en",
    prefilter_config: PrefilterConfig | None = None,
) -> BriefResult:
    """Ingest the requested time range, run the engine, and return its coverage."""
    repo = InMemoryRepository()
    await repo.set_global_interests([Interest(text) for text in (interests or tokens)])
    source_ids: list[int] = []
    errors: list[str] = []
    complete = True
    start = now - window
    if reader is not None and resolver is not None:
        coordinator = IngestionCoordinator(store, reader, resolver=resolver, limits=limits)
        for token in tokens:
            try:
                resolved = await coordinator.resolve_public_ref(token)
                source_ids.append(resolved.id)
                await repo.add_channel(
                    Channel(telegram_ref=token, name=token, source_id=resolved.id)
                )
            except Exception as exc:
                complete = False
                errors.append(f"{token}: {exc}")
        if source_ids:
            result = await coordinator.ensure_window(source_ids, start, now)
            errors.extend(f"source {sid}: {reason}" for sid, reason in result.errors.items())
            complete = complete and all(result[sid].complete for sid in source_ids)
    if reader is None and hasattr(store, "fetch_new_items"):
        feed_source: FeedSource = store
        complete = True
        source_errors = getattr(store, "errors", {})
        errors.extend(f"{ref}: {message}" for ref, message in source_errors.items())
        complete = not errors
        for token in tokens:
            await repo.add_channel(Channel(telegram_ref=token, name=token))
    else:
        active_limits = limits or IngestionLimits()
        feed_source = WindowSource(
            store,
            repo=repo,
            max_posts_per_channel=active_limits.max_posts_per_channel,
            max_posts_per_run=active_limits.max_posts_per_run,
            start=start,
            end=now,
        )
    pipeline = Pipeline(
        source=feed_source,
        llm=llm,
        repo=repo,
        prefilter_config=prefilter_config,
    )
    await pipeline.run_tick(ignore_cursor=True)
    report = await ReportService(repo=repo, llm=llm, language=language).prepare()
    truncated = bool(getattr(feed_source, "truncated", False))
    coverage = BriefCoverage(complete=complete, truncated=truncated, errors=tuple(errors))
    text = _markdown("\n\n".join(report.chunks))
    if not coverage.complete or coverage.truncated:
        details = "; ".join(coverage.errors) or (
            "source limits reached" if coverage.truncated else "unknown source coverage"
        )
        notice = f"## Coverage\nINCOMPLETE — this brief may omit events. {details}."
        text = f"{text}\n\n{notice}" if text else notice
    elif not text:
        text = "No significant items were found in the selected window."
    return BriefResult(markdown=text, coverage=coverage)
