from datetime import UTC, datetime

from astrafeed.application.agenda_query import search_in_snapshot
from astrafeed.domain.agenda import CoverageInfo, SearchDoc, Snapshot, StoryCard


def test_search_matches_multiple_terms_and_russian_inflections_across_evidence():
    now = datetime(2026, 9, 24, tzinfo=UTC)
    snapshot = Snapshot(
        snapshot_id="search",
        t=now,
        collected_at=now,
        analyzed_at=now,
        published_at=now,
        coverage=CoverageInfo(2, 0, 0, 2, 2, 0, 0, 2),
        queue_depth=0,
        limitations=(),
        agenda=(),
        agenda_mode="full",
        search_docs=(
            SearchDoc("rub", "title", "Правительство переводит контракты в цифровые рубли"),
            SearchDoc("zec", "title", "Крупные транзакции на крипторынке"),
            SearchDoc("zec", "entity", "Гаррет Джин"),
            SearchDoc("zec", "claim", "Гаррет закрыл шорт ZEC"),
            SearchDoc("rwa", "title", "Рынок токенизированных RWA вырос"),
        ),
    )
    for query, expected in (
        ("цифровой рубль", "rub"),
        ("ZEC шорт Гаррет", "zec"),
        ("RWA токенизация", "rwa"),
    ):
        hits, _ = search_in_snapshot(snapshot, query, limit=5, offset=0)
        assert hits and hits[0].story_id == expected


def test_search_shows_published_english_title_while_matching_original_title():
    now = datetime(2026, 9, 24, tzinfo=UTC)
    card = StoryCard(
        story_id="hype",
        title="Binance lists HYPE",
        entities=("HYPE",),
        current_channels=2,
        previous_channels=0,
        growth=2,
        growth_null_reason=None,
        first_seen=now,
        freshness=now,
        explanation="",
        claims=(),
    )
    snapshot = Snapshot(
        snapshot_id="search",
        t=now,
        collected_at=now,
        analyzed_at=now,
        published_at=now,
        coverage=CoverageInfo(2, 0, 0, 2, 2, 0, 0, 2),
        queue_depth=0,
        limitations=(),
        agenda=(card,),
        agenda_mode="full",
        search_docs=(SearchDoc("hype", "title", "Binance листит HYPE"),),
    )

    hits, _ = search_in_snapshot(snapshot, "листит HYPE", limit=5, offset=0)

    assert hits[0].title == "Binance lists HYPE"
    assert "Binance листит HYPE" in hits[0].matched
