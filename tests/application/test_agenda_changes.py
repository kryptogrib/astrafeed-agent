from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.adapters.repository.memory_agenda import InMemoryAgendaStore
from astrafeed.application.agenda_query import agenda_payload, render_agenda_html
from astrafeed.domain.agenda import PriceMove, PublicationRef, SourceNode, StorySignals
from tests.adapters.http.test_agenda import _snapshot

T = datetime(2026, 9, 25, 12, tzinfo=UTC)


def _pair():
    before = replace(_snapshot(T), snapshot_id="snap-before")
    after = replace(
        before,
        snapshot_id="snap-after",
        t=T + timedelta(hours=1),
        collected_at=T + timedelta(hours=1),
        analyzed_at=T + timedelta(hours=1),
        published_at=T + timedelta(hours=1),
    )
    return before, after


async def _read(before, after, **kwargs):
    store = InMemoryAgendaStore()
    await store.publish_snapshot(before)
    await store.publish_snapshot(after)
    return await agenda_payload(store, snapshot_id=None, now=after.published_at, **kwargs)


async def test_without_baseline_returns_the_existing_full_agenda():
    before, after = _pair()
    result = await _read(before, after)
    assert result["stories"][0]["story_id"] == "st-eth"
    assert "changes" not in result


async def test_same_snapshot_returns_an_empty_delta_not_an_empty_agenda_claim():
    before, after = _pair()
    result = await _read(before, after, since_snapshot_id="snap-after")
    assert result["snapshot_id"] == result["compared_to"] == "snap-after"
    assert result["comparison_status"] == "ok"
    assert result["response_mode"] == "delta"
    assert result["changes"] == {"new_stories": [], "updated_stories": [], "removed_stories": []}
    assert result["stories"] == result["upcoming"] == []
    assert result["agenda_story_ids"] == ["st-eth"]
    assert "No changes" in result["brief_markdown"]
    assert "No changes" in render_agenda_html(result)
    assert "No new or growing stories" not in result["brief_markdown"]


async def test_new_publications_have_sources_echoes_and_late_arrival_context():
    before, after = _pair()
    old = before.stories["st-eth"]
    echo = PublicationRef(
        "2:20",
        "@echo",
        "https://t.me/echo/20",
        T + timedelta(minutes=5),
        old.publications[0].quote,
    )
    late = PublicationRef(
        "3:30",
        "@late",
        "https://t.me/late/30",
        T - timedelta(minutes=10),
        "ETH ETF outflow was more than $170 million.",
    )
    signals = StorySignals(
        sources=(
            SourceNode("@alpha", old.publications[0].link, T - timedelta(hours=2), 0),
            SourceNode("@late", late.link, late.published_at, 110),
            SourceNode("@echo", echo.link, echo.published_at, 125, echo_of="@alpha"),
        )
    )
    card = replace(old.card, current_channels=3, signals=signals)
    after = replace(
        after,
        agenda=(card,),
        stories={"st-eth": replace(old, card=card, publications=(*old.publications, echo, late))},
    )

    result = await _read(before, after, since_snapshot_id="snap-before")

    change = result["changes"]["updated_stories"][0]
    assert change["added_channels"] == ["@echo", "@late"]
    assert change["added_echo_channels"] == ["@echo"]
    assert {p["publication_id"] for p in change["added_publications"]} == {"2:20", "3:30"}
    pubs = {p["publication_id"]: p for p in change["added_publications"]}
    assert pubs["2:20"]["published_since_baseline"] is True
    assert pubs["3:30"]["published_since_baseline"] is False
    assert pubs["3:30"]["quote"] == "ETH ETF outflow was more than $170 million."
    assert pubs["3:30"]["link"] == "https://t.me/late/30"
    assert result["stories"][0]["story_id"] == "st-eth"
    assert result["compared_to"] == "snap-before"
    assert "2 publications added" in result["brief_markdown"]
    assert "snap-before" in render_agenda_html(result)


async def test_changed_quote_and_sourcing_are_reported_with_before_and_after():
    before, after = _pair()
    old = before.stories["st-eth"]
    old_card = replace(old.card, signals=StorySignals(confirmation="rumor"))
    before = replace(before, agenda=(old_card,), stories={"st-eth": replace(old, card=old_card)})
    claim = replace(old.card.claims[0], quote="ETH ETF outflow exceeds $170m.")
    card = replace(
        old.card,
        claims=(claim,),
        signals=StorySignals(confirmation="attributed", attributed_to=("Arkham",)),
    )
    after = replace(
        after,
        agenda=(card,),
        stories={
            "st-eth": replace(
                old, card=card, publications=(replace(old.publications[0], quote=claim.quote),)
            )
        },
    )
    result = await _read(before, after, since_snapshot_id="snap-before")
    change = result["changes"]["updated_stories"][0]
    assert change["added_publications"] == []
    assert change["changed_quotes"][0]["before"] == old.publications[0].quote
    assert change["changed_quotes"][0]["after"] == claim.quote
    assert change["changed_quotes"][0]["link"] == claim.link
    assert change["sourcing"] == {
        "before": {"confirmation": "rumor", "attributed_to": []},
        "after": {"confirmation": "attributed", "attributed_to": ["Arkham"]},
    }


async def test_translation_title_order_and_freshness_do_not_create_news():
    before, after = _pair()
    detail = before.stories["st-eth"]
    card = replace(
        detail.card,
        title="ETH ETF flows",
        explanation="A new translation",
        freshness=T + timedelta(minutes=50),
        claims=(replace(detail.card.claims[0], translation="Translated quote"),),
    )
    after = replace(
        after,
        agenda=(card,),
        stories={
            "st-eth": replace(detail, card=card, publications=tuple(reversed(detail.publications)))
        },
    )
    result = await _read(before, after, since_snapshot_id="snap-before")
    assert result["stories"] == []
    assert result["changes"]["updated_stories"] == []


async def test_new_claim_in_the_same_publication_is_not_lost_behind_its_first_quote():
    before, after = _pair()
    old = before.stories["st-eth"]
    added = replace(old.card.claims[0], quote="The issuer says withdrawals are open.")
    card = replace(old.card, claims=(*old.card.claims, added))
    after = replace(after, agenda=(card,), stories={"st-eth": replace(old, card=card)})
    result = await _read(before, after, since_snapshot_id="snap-before")
    change = result["changes"]["updated_stories"][0]
    assert change["added_publications"] == []
    assert change["added_claims"][0]["quote"] == added.quote
    assert change["added_claims"][0]["link"] == added.link


async def test_price_updates_and_coverage_changes_do_not_resend_unchanged_evidence():
    before, after = _pair()
    old = before.stories["st-eth"]
    move = PriceMove("ETH-USDT", T, 100, 101, 1.0, T)
    card = replace(old.card, signals=StorySignals(price=move))
    before = replace(before, agenda=(card,), stories={"st-eth": replace(old, card=card)})
    later = replace(card, signals=replace(card.signals, price=replace(move, price_now=102)))
    after = replace(
        after,
        agenda=(later,),
        stories={"st-eth": replace(old, card=later)},
        coverage=replace(after.coverage, channels_incomplete=1),
        limitations=("processing_in_progress",),
    )
    result = await _read(before, after, since_snapshot_id="snap-before")
    assert result["changes"]["updated_stories"] == []
    assert result["baseline_coverage"]["channels_incomplete"] == 0
    assert result["coverage"]["channels_incomplete"] == 1
    assert result["limitations"] == ["processing_in_progress"]


async def test_new_to_agenda_is_distinguished_from_previously_unknown_story():
    before, after = _pair()
    detail = before.stories["st-eth"]
    known = replace(detail.card, story_id="st-known", title="Known outside the top ten")
    new = replace(detail.card, story_id="st-new", title="New story")
    before = replace(before, stories={**before.stories, "st-known": replace(detail, card=known)})
    after = replace(
        after,
        agenda=(known, new),
        stories={"st-known": replace(detail, card=known), "st-new": replace(detail, card=new)},
    )
    result = await _read(before, after, since_snapshot_id="snap-before")
    additions = result["changes"]["new_stories"]
    assert [(s["story_id"], s["previously_known"]) for s in additions] == [
        ("st-known", True),
        ("st-new", False),
    ]
    assert result["changes"]["removed_stories"][0]["story_id"] == "st-eth"
    assert result["agenda_story_ids"] == ["st-known", "st-new"]


async def test_calendar_entries_and_section_moves_are_included():
    before, after = _pair()
    after = replace(after, agenda=(), upcoming=after.agenda)
    result = await _read(before, after, since_snapshot_id="snap-before")
    change = result["changes"]["updated_stories"][0]
    assert change["section"] == "upcoming"
    assert change["previous_section"] == "agenda"
    assert result["upcoming"][0]["story_id"] == "st-eth"
    assert result["stories"] == []
    assert "On the calendar" in result["brief_markdown"]


async def test_unknown_baseline_returns_full_agenda_with_unavailable_comparison():
    before, after = _pair()
    result = await _read(before, after, since_snapshot_id="missing<script>")
    assert result["response_mode"] == "full"
    assert result["comparison_status"] == "baseline_unavailable"
    assert result["compared_to"] is None
    assert result["since_snapshot_id"] == "missing<script>"
    assert result["changes"] is None
    assert result["stories"][0]["story_id"] == "st-eth"
    assert "unavailable" in result["brief_markdown"]
    assert "<script>" not in render_agenda_html(result)


async def test_target_can_be_pinned_and_newer_baseline_is_rejected():
    before, after = _pair()
    store = InMemoryAgendaStore()
    await store.publish_snapshot(before)
    await store.publish_snapshot(after)
    await store.publish_snapshot(replace(after, snapshot_id="snap-latest", agenda=()))
    result = await agenda_payload(
        store, snapshot_id="snap-after", since_snapshot_id="snap-before", now=T
    )
    assert result["snapshot_id"] == "snap-after"
    assert result["agenda_story_ids"] == ["st-eth"]
    with pytest.raises(ValueError, match="newer"):
        await agenda_payload(
            store, snapshot_id="snap-before", since_snapshot_id="snap-after", now=T
        )


@pytest.mark.parametrize("baseline", ["", "   "])
async def test_blank_baseline_is_not_silently_ignored(baseline):
    before, after = _pair()
    with pytest.raises(ValueError, match="since_snapshot_id"):
        await _read(before, after, since_snapshot_id=baseline)


async def test_minimal_snapshots_do_not_treat_reordered_excerpts_as_post_edits():
    before, after = _pair()
    card = before.agenda[0]
    second = replace(card.claims[0], quote="A second excerpt from the same post.")
    before = replace(before, stories={}, agenda=(replace(card, claims=(*card.claims, second)),))
    after = replace(after, stories={}, agenda=(replace(card, claims=(second, *card.claims)),))
    result = await _read(before, after, since_snapshot_id="snap-before")
    assert result["changes"]["updated_stories"] == []


async def test_minimal_baseline_does_not_invent_publication_additions_when_detail_appears():
    before, after = _pair()
    before = replace(before, stories={})
    result = await _read(before, after, since_snapshot_id="snap-before")
    assert result["changes"]["updated_stories"] == []
    assert result["comparison_limitations"] == ["publication_details_unavailable"]
    assert "unavailable" in result["brief_markdown"]

    detail = after.stories["st-eth"]
    claim = replace(detail.card.claims[0], quote="Another source statement.")
    card = replace(detail.card, claims=(*detail.card.claims, claim))
    after = replace(after, agenda=(card,), stories={"st-eth": replace(detail, card=card)})
    result = await _read(before, after, since_snapshot_id="snap-before")
    change = result["changes"]["updated_stories"][0]
    assert change["added_publications"] is None
    assert change["removed_publication_ids"] is None
    assert change["added_channels"] is None
    assert change["changed_quotes"] is None
    assert change["added_claims"][0]["quote"] == claim.quote
