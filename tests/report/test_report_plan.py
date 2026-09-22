from __future__ import annotations

from astrafeed.report.dedup import MergedItem
from astrafeed.report.plan import ReportGroup, ReportPlan, code_default_plan, validate_plan


def _m(imp: int, interest: str, gist: str) -> MergedItem:
    return MergedItem(
        gist=gist,
        importance=imp,
        interests=(interest,),
        sources=(("h", "https://t.me/h/1"),),
        cluster_id=gist,
    )


def test_code_default_plan_groups_by_interest_sorted_desc():
    kept = [_m(2, "AI", "a"), _m(5, "AI", "b"), _m(3, "Crypto", "c")]
    plan = code_default_plan(kept)
    assert plan.overview is None
    ai = next(g for g in plan.groups if g.title == "AI")
    assert ai.item_ids == ["1", "0"]  # importance 5 (idx1) before 2 (idx0)


def test_validate_drops_unknown_ids_and_appends_missing():
    kept = [_m(4, "AI", "a"), _m(3, "AI", "b")]  # ids "0","1"
    raw = ReportPlan(
        overview="hi",
        groups=[
            ReportGroup(title="AI", item_ids=["0", "99"], insight=None),  # 99 unknown
        ],
    )
    clean = validate_plan(raw, kept, mode="format")
    all_ids = [i for g in clean.groups for i in g.item_ids]
    assert "99" not in all_ids
    assert set(all_ids) == {"0", "1"}  # missing "1" appended to a tail group


def test_validate_strips_insight_in_format_mode():
    kept = [_m(4, "AI", "a"), _m(3, "AI", "b")]
    raw = ReportPlan(
        overview=None,
        groups=[
            ReportGroup(title="AI", item_ids=["0", "1"], insight="two channels carried this"),
        ],
    )
    clean = validate_plan(raw, kept, mode="format")
    assert clean.groups[0].insight is None


def test_validate_strips_insight_with_fewer_than_two_ids():
    kept = [_m(4, "AI", "a")]
    raw = ReportPlan(
        overview=None,
        groups=[
            ReportGroup(title="AI", item_ids=["0"], insight="solo theme"),
        ],
    )
    clean = validate_plan(raw, kept, mode="insights")
    assert clean.groups[0].insight is None


def test_validate_dedupes_id_across_groups():
    kept = [_m(4, "AI", "a"), _m(3, "AI", "b")]
    raw = ReportPlan(
        groups=[
            ReportGroup(title="X", item_ids=["0", "1"]),
            ReportGroup(title="Y", item_ids=["0"]),
        ]
    )
    clean = validate_plan(raw, kept, mode="format")
    all_ids = [i for g in clean.groups for i in g.item_ids]
    assert all_ids.count("0") == 1


def test_validate_normalizes_empty_overview_to_none():
    kept = [_m(4, "AI", "a")]
    raw = ReportPlan(overview="", groups=[ReportGroup(title="AI", item_ids=["0"])])
    clean = validate_plan(raw, kept, mode="format")
    assert clean.overview is None


def test_validate_keeps_numberless_insight_in_insights_mode():
    kept = [_m(4, "AI", "alpha"), _m(3, "AI", "beta")]
    raw = ReportPlan(
        groups=[
            ReportGroup(title="AI", item_ids=["0", "1"], insight="both channels agree"),
        ]
    )
    clean = validate_plan(raw, kept, mode="insights")
    assert clean.groups[0].insight == "both channels agree"


def test_validate_strips_fabricated_number_in_insight():
    kept = [_m(4, "AI", "no digits here"), _m(3, "AI", "also clean")]
    raw = ReportPlan(
        overview=None,
        groups=[
            ReportGroup(title="AI", item_ids=["0", "1"], insight="3 channels confirmed it"),
        ],
    )
    clean = validate_plan(raw, kept, mode="insights")
    assert clean.groups[0].insight is None  # "3" not present in any cited gist
