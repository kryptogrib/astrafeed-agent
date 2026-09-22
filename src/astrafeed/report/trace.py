from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from astrafeed.report.dedup import MergedItem
from astrafeed.report.events import ComponentJudgment, EventBlock, EventJudgeResult
from astrafeed.report.plan import ReportPlan

PointKind = Literal["item", "event", "reverted"]


@dataclass(frozen=True)
class RenderedPoint:
    """One actually emitted Report bullet/block after render-time decisions."""

    kind: PointKind
    item_ids: tuple[str, ...]
    subfacts: tuple[str, ...] = ()
    subfacts_dropped: int = 0
    text: str = ""
    # (channel_ref, external_id) pairs — source-qualified membership (T05), so two
    # sources sharing a bare external_id are never conflated by ``item_ids`` alone.
    material_keys: tuple[tuple[str, str], ...] = ()


class RenderObserver(Protocol):
    """Audit hook: called once per rendered point. Same contract as PrefilterObserver."""

    def __call__(self, *, point: RenderedPoint) -> None: ...


@dataclass
class ReportTrace:
    """Two-level trace: service stages plus the points the renderer actually emitted."""

    merged: list[tuple[str, ...]] = field(default_factory=list)
    cutoff_kept: list[tuple[str, ...]] = field(default_factory=list)
    cutoff_hidden: list[tuple[str, ...]] = field(default_factory=list)
    event_components: list[tuple[str, ...]] = field(default_factory=list)
    event_component_members: list[list[tuple[str, ...]]] = field(default_factory=list)
    event_judgments: list[ComponentJudgment] = field(default_factory=list)
    plan_groups: list[tuple[str, ...]] = field(default_factory=list)
    stage_failures: list[str] = field(default_factory=list)
    rendered_points: list[RenderedPoint] = field(default_factory=list)

    def __call__(self, *, point: RenderedPoint) -> None:
        self.rendered_points.append(point)

    def record_merged(self, items: Sequence[MergedItem]) -> None:
        self.merged = [item_ids_of(m) for m in items]

    def record_cutoff(self, kept: Sequence[MergedItem], hidden: Sequence[MergedItem]) -> None:
        self.cutoff_kept = [item_ids_of(m) for m in kept]
        self.cutoff_hidden = [item_ids_of(m) for m in hidden]

    def record_event_components(self, components: Sequence[Sequence[MergedItem]]) -> None:
        self.event_component_members = [[item_ids_of(m) for m in comp] for comp in components]
        self.event_components = [item_ids_of(m) for comp in components for m in comp]

    def record_event_judgments(self, result: EventJudgeResult) -> None:
        self.event_judgments = list(result.components)

    def record_plan(self, plan: ReportPlan) -> None:
        self.plan_groups = [tuple(g.item_ids) for g in plan.groups]


def item_ids_of(m: MergedItem) -> tuple[str, ...]:
    if m.member_item_ids:
        return tuple(eid for _ch, eid in m.member_item_ids)
    if m.representative_item is not None:
        return (m.representative_item.external_id,)
    return ()


def material_keys_of(m: MergedItem) -> tuple[tuple[str, str], ...]:
    if m.member_item_ids:
        return tuple(m.member_item_ids)
    if m.representative_item is not None:
        rep = m.representative_item
        return ((rep.channel_ref, rep.external_id),)
    return ()


def event_item_ids(block: EventBlock) -> tuple[str, ...]:
    return tuple(eid for _ch, eid in block.member_item_ids)


def event_material_keys(block: EventBlock) -> tuple[tuple[str, str], ...]:
    return tuple(block.member_item_ids)
