from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from astrafeed.domain import Interest, Item, Verdict
from astrafeed.report.dedup import MergedItem
from astrafeed.report.events import EventJudgeResult
from astrafeed.report.plan import ReportPlan


class LLMClient(Protocol):
    async def score(
        self, items: Sequence[Item], effective_interests: Sequence[Interest]
    ) -> list[Verdict]:
        """ONE batched cheap-model call: one Verdict per input Item, same order."""
        ...

    async def compose_report(
        self, items: Sequence[MergedItem], *, mode: str, language: str
    ) -> ReportPlan:
        """Strong model: return a validated editorial plan (overview + groups)."""
        ...

    async def judge_events(
        self, components: Sequence[Sequence[MergedItem]], *, language: str
    ) -> EventJudgeResult:
        """Cheap model, ONE batched call: partition each cross-channel candidate
        component into events. Returns a nested-per-component result positionally
        aligned with ``components`` (ids are component-local)."""
        ...
