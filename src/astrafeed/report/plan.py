from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from astrafeed.report.dedup import MergedItem
from astrafeed.report.grouping import UNCATEGORIZED

_NUM_RE = re.compile(r"\d+")
_TAIL_TITLE = UNCATEGORIZED


@dataclass(frozen=True)
class ReportGroup:
    title: str
    item_ids: list[str] = field(default_factory=list)
    insight: str | None = None


@dataclass(frozen=True)
class ReportPlan:
    overview: str | None = None
    groups: list[ReportGroup] = field(default_factory=list)


def code_default_plan(orphans: Sequence[MergedItem]) -> ReportPlan:
    """Deterministic grouping used in editorial_mode=off and as the fallback:
    group by first interest, sort each group by importance desc (stable)."""
    by_interest: dict[str, list[int]] = {}
    order: list[str] = []
    for idx, m in enumerate(orphans):
        label = m.interests[0] if m.interests else UNCATEGORIZED
        if label not in by_interest:
            by_interest[label] = []
            order.append(label)
        by_interest[label].append(idx)
    groups: list[ReportGroup] = []
    for label in order:
        # ties preserve input order intentionally (stable sort on importance desc)
        idxs = sorted(by_interest[label], key=lambda i: orphans[i].importance, reverse=True)
        groups.append(ReportGroup(title=label, item_ids=[str(i) for i in idxs]))
    return ReportPlan(overview=None, groups=groups)


def validate_plan(plan: ReportPlan, orphans: Sequence[MergedItem], *, mode: str) -> ReportPlan:
    """Trust boundary over the strong model's output. Drops unknown ids,
    de-dupes, appends omitted ids to a tail group, and strips insights that
    are disallowed (mode), under-cited (<2 ids), or contain a number absent
    from every cited gist."""
    known = {str(i) for i in range(len(orphans))}
    seen: set[str] = set()
    clean_groups: list[ReportGroup] = []
    for g in plan.groups:
        ids: list[str] = []
        for i in g.item_ids:
            if i in known and i not in seen:
                ids.append(i)
                seen.add(i)
        if not ids:
            continue
        insight = _clean_insight(g.insight, ids, orphans, mode)
        clean_groups.append(
            ReportGroup(title=g.title or UNCATEGORIZED, item_ids=ids, insight=insight)
        )

    missing = [i for i in known if i not in seen]
    if missing:
        # break importance ties by original index for deterministic ordering
        tail_ids = sorted(missing, key=lambda s: (-orphans[int(s)].importance, int(s)))
        existing_tail = next((g for g in clean_groups if g.title == _TAIL_TITLE), None)
        if existing_tail is not None:
            # merge into the model's existing tail group rather than duplicating it
            merged = ReportGroup(
                title=existing_tail.title,
                item_ids=existing_tail.item_ids + tail_ids,
                insight=existing_tail.insight,
            )
            clean_groups = [merged if g is existing_tail else g for g in clean_groups]
        else:
            clean_groups.append(ReportGroup(title=_TAIL_TITLE, item_ids=tail_ids))
    return ReportPlan(overview=(plan.overview or None), groups=clean_groups)


def _clean_insight(
    insight: str | None, ids: list[str], orphans: Sequence[MergedItem], mode: str
) -> str | None:
    if not insight or mode != "insights" or len(ids) < 2:
        return None
    cited = " ".join(orphans[int(i)].gist for i in ids)
    cited_nums = set(_NUM_RE.findall(cited))
    if any(n not in cited_nums for n in _NUM_RE.findall(insight)):
        return None  # fabricated number/date
    return insight
