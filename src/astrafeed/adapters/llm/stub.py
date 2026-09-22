from __future__ import annotations

from collections.abc import Sequence

from astrafeed.domain import Interest, Item, Route, Verdict
from astrafeed.report.dedup import MergedItem
from astrafeed.report.events import ComponentJudgment, EventJudgeResult
from astrafeed.report.plan import ReportPlan


class StubLLMClient:
    """Scripted Verdicts; records that score() was called once per tick."""

    def __init__(
        self, route_for: dict[str, Verdict] | None = None, default_route: Route = Route.DROP
    ) -> None:
        self._route_for = route_for or {}
        self._default = default_route
        self.score_calls = 0
        self.last_batch_size = 0

    async def score(
        self, items: Sequence[Item], effective_interests: Sequence[Interest]
    ) -> list[Verdict]:
        self.score_calls += 1
        self.last_batch_size = len(items)
        out: list[Verdict] = []
        for item in items:
            v = self._route_for.get(item.external_id)
            out.append(v if v is not None else Verdict(item=item, route=self._default))
        return out

    async def compose_report(
        self, items: Sequence[MergedItem], *, mode: str, language: str
    ) -> ReportPlan:
        return ReportPlan()

    async def judge_events(
        self, components: Sequence[Sequence[MergedItem]], *, language: str
    ) -> EventJudgeResult:
        # Deterministic default: every member of every component is rejected to its
        # own bullet, so the stub never manufactures a merge and existing report
        # output stays byte-identical.
        return EventJudgeResult(
            components=tuple(
                ComponentJudgment(groups=(), rejected_ids=tuple(str(i) for i in range(len(comp))))
                for comp in components
            )
        )
