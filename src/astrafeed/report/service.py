"""Compose queued verdicts into a concise rendered report."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from astrafeed.domain.report import PreparedReport, ReportAcknowledgement
from astrafeed.ports.llm import LLMClient
from astrafeed.ports.repository import Repository
from astrafeed.report.dedup import MergedItem, dedup_for_report
from astrafeed.report.events import EventBlock, assemble_components, merge_events
from astrafeed.report.plan import ReportPlan, code_default_plan, validate_plan
from astrafeed.report.render import render_report


class ReportService:
    def __init__(
        self,
        *,
        repo: Repository,
        llm: LLMClient,
        language: str = "en",
        window_hours: int = 24,
        editorial_mode: str = "format",
        report_min_importance: int = 1,
        event_merge_enabled: bool = True,
        trace: Any | None = None,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._language = language
        self._window_hours = window_hours
        self._editorial_mode = editorial_mode
        self._report_min_importance = report_min_importance
        self._event_merge_enabled = event_merge_enabled
        self._trace = trace

    async def prepare(self) -> PreparedReport:
        rows = await self._repo.peek_report_queue()
        if not rows:
            return PreparedReport((), ReportAcknowledgement())
        ids, verdicts = zip(*rows, strict=True)
        merged = dedup_for_report(verdicts)
        kept = [m for m in merged if m.importance >= self._report_min_importance]
        hidden = len(merged) - len(kept)
        if self._trace is not None:
            self._trace.record_merged(merged)
            self._trace.record_cutoff(
                kept, [m for m in merged if m.importance < self._report_min_importance]
            )

        blocks: list[EventBlock] = []
        consumed: list[MergedItem] = []
        if self._event_merge_enabled:
            components = assemble_components(kept)
            if components:
                judged = await self._llm.judge_events(components, language=self._language)
                blocks, consumed = merge_events(components, judged)
        consumed_keys = {key for item in consumed for key in item.member_item_ids}
        orphans = [m for m in kept if not any(key in consumed_keys for key in m.member_item_ids)]
        plan: ReportPlan
        if orphans:
            plan = await self._llm.compose_report(
                orphans, mode=self._editorial_mode, language=self._language
            )
            plan = validate_plan(plan, orphans, mode=self._editorial_mode)
        else:
            plan = code_default_plan([])
        member_lookup = {key: item for item in kept for key in item.member_item_ids}
        parts = render_report(
            sorted(blocks, key=lambda block: -block.importance),
            plan,
            orphans,
            hidden_count=hidden,
            run_time=datetime.now(UTC),
            language=self._language,
            window_hours=self._window_hours,
            member_lookup=member_lookup,
        )
        return PreparedReport(
            tuple(parts), ReportAcknowledgement(queue_ids=tuple(ids), composed_at=datetime.now(UTC))
        )

    async def compose(self) -> list[str]:
        return list((await self.prepare()).chunks)
