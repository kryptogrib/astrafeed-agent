from datetime import UTC, datetime, timedelta

from astrafeed.domain.agenda import (
    CLASSIFIER_VERSION,
    agenda_rank_key,
    analysis_reuse_key,
    comparable_channel_ids,
    numbers_are_grounded,
    rank_agenda_stories,
    resolve_quote_span,
    resolve_relative_when,
    text_hash,
    windows_at,
)


def test_quote_accepted_only_when_span_matches_or_unique_occurrence():
    text = "Отток ETH ETF составил $120 млн. Это слабо."
    assert resolve_quote_span(text, "Отток ETH ETF составил $120 млн.", 0, 32) == (0, 32)
    assert resolve_quote_span(text, "Это слабо.", 99, 100) == (33, 43)
    repeated = "ETH вырос. Спорят про ETH."
    assert resolve_quote_span(repeated, "ETH", 0, 3) == (0, 3)
    assert resolve_quote_span(repeated, "ETH", 99, 100) is None
    assert resolve_quote_span(text, "нет такой цитаты", 0, 5) is None
    assert resolve_quote_span(text, "", 0, 0) is None


def test_same_text_reuses_extraction_across_publications():
    h = text_hash("один и тот же текст")
    assert h == text_hash("один и тот же текст")
    assert h != text_hash("другой текст")
    a = analysis_reuse_key(h, CLASSIFIER_VERSION)
    b = analysis_reuse_key(text_hash("один и тот же текст"), CLASSIFIER_VERSION)
    assert a == b
    assert analysis_reuse_key(h, "open-extract/v5") != a


def test_windows_are_half_open_24h_pairs():
    t = datetime(2026, 9, 24, 21, 0, tzinfo=UTC)
    current, previous = windows_at(t)
    assert current == (t - timedelta(hours=24), t)
    assert previous == (t - timedelta(hours=48), t - timedelta(hours=24))
    assert current[0] == previous[1]
    assert current[1] != current[0]


def test_paraphrase_cannot_invent_numbers_absent_from_quotes():
    quotes = ["Отток составил $120 млн"]
    assert numbers_are_grounded("Авторы пишут об оттоке $120 млн", quotes)
    assert not numbers_are_grounded("Авторы пишут об оттоке $240 млн", quotes)
    assert numbers_are_grounded("Авторы называют отток слабым спросом", quotes)


def test_today_and_yesterday_resolve_per_publication_instance():
    published = datetime(2026, 9, 23, 15, 0, tzinfo=UTC)
    assert resolve_relative_when("сегодня", published) == "2026-09-23"
    assert resolve_relative_when("вчера", published) == "2026-09-22"
    assert resolve_relative_when("22 сентября", published) == "22 сентября"


def test_comparable_channels_require_complete_processing_of_both_windows():
    comparable = comparable_channel_ids(
        {
            1: {"current_complete": True, "previous_complete": True, "processed": True},
            2: {"current_complete": True, "previous_complete": False, "processed": True},
            3: {"current_complete": True, "previous_complete": True, "processed": False},
            4: {"current_complete": True, "previous_complete": True, "processed": True},
        }
    )
    assert comparable == frozenset({1, 4})


def test_agenda_sorts_by_growth_then_channels_then_freshness_then_id():
    t = datetime(2026, 9, 24, tzinfo=UTC)
    stories = [
        {
            "story_id": "st-b",
            "growth": 2,
            "current_channels": 3,
            "freshness": t,
            "eligible": True,
        },
        {
            "story_id": "st-a",
            "growth": 2,
            "current_channels": 3,
            "freshness": t,
            "eligible": True,
        },
        {
            "story_id": "st-c",
            "growth": 3,
            "current_channels": 2,
            "freshness": t,
            "eligible": True,
        },
        {
            "story_id": "st-d",
            "growth": 1,
            "current_channels": 4,
            "freshness": t,
            "eligible": False,
        },
    ]
    ranked = rank_agenda_stories(stories)
    assert [s["story_id"] for s in ranked] == ["st-c", "st-a", "st-b"]
    assert agenda_rank_key(stories[2]) < agenda_rank_key(stories[1])


def test_growth_is_null_when_comparable_set_is_too_small():
    from astrafeed.domain.agenda import decide_growth

    growth, reason = decide_growth(
        current_channels=3,
        previous_channels=1,
        comparable_count=1,
        previous_window_complete=True,
    )
    assert growth is None
    assert reason == "comparable_channels_below_2"

    growth, reason = decide_growth(
        current_channels=3,
        previous_channels=1,
        comparable_count=4,
        previous_window_complete=True,
    )
    assert growth == 2
    assert reason is None

    growth, reason = decide_growth(
        current_channels=2,
        previous_channels=0,
        comparable_count=4,
        previous_window_complete=True,
    )
    assert growth == 2


def test_empty_agenda_when_full_compare_has_no_new_or_growing_stories():
    from astrafeed.domain.agenda import select_agenda

    cards = [
        {
            "story_id": "st-flat",
            "growth": 0,
            "current_channels": 3,
            "previous_channels": 3,
            "eligible": True,
        }
    ]
    selected, mode = select_agenda(cards, comparable_count=4)
    assert selected == []
    assert mode == "empty_no_growth"

    limited = [
        {
            "story_id": "st-multi",
            "growth": None,
            "current_channels": 2,
            "previous_channels": None,
            "eligible": True,
        }
    ]
    selected, mode = select_agenda(limited, comparable_count=1)
    assert [c["story_id"] for c in selected] == ["st-multi"]
    assert mode == "limited_no_growth_claim"


def test_agenda_limits_each_confirmed_primary_entity_to_two_without_losing_stories():
    from astrafeed.domain.agenda import select_agenda

    cards = [
        {
            "story_id": f"var-{index}",
            "growth": 10 - index,
            "current_channels": 3,
            "eligible": True,
            "primary_entity": "variational",
        }
        for index in range(4)
    ] + [
        {
            "story_id": "other",
            "growth": 5,
            "current_channels": 3,
            "eligible": True,
            "primary_entity": "payy",
        }
    ]
    selected, _ = select_agenda(cards, comparable_count=4)
    assert [item["story_id"] for item in selected] == ["var-0", "var-1", "other"]
    assert len(cards) == 5


def test_agenda_limits_stories_from_identical_publication_sets():
    from astrafeed.domain.agenda import select_agenda

    cards = [
        {
            "story_id": f"digest-{index}",
            "growth": 10 - index,
            "current_channels": 2,
            "eligible": True,
            "source_signature": ("channel-a:1", "channel-b:2"),
        }
        for index in range(4)
    ] + [
        {
            "story_id": "independent",
            "growth": 2,
            "current_channels": 2,
            "eligible": True,
            "source_signature": ("channel-c:3", "channel-d:4"),
        }
    ]
    selected, _ = select_agenda(cards, comparable_count=4)
    assert [item["story_id"] for item in selected] == ["digest-0", "independent"]
    assert len(cards) == 5


def test_agenda_shows_one_retelling_of_same_entity_pair_and_event():
    from astrafeed.domain.agenda import select_agenda

    first = datetime(2026, 9, 24, 12, 5, tzinfo=UTC)
    cards = [
        {
            "story_id": "portfolios",
            "title": "BlackRock и Ondo Finance запускают токенизированные инвестпортфели",
            "entities": ("BlackRock", "Ondo Finance"),
            "first_seen": first,
            "growth": 5,
            "current_channels": 5,
            "eligible": True,
        },
        {
            "story_id": "partnership",
            "title": "ONDO объявляет о партнерстве с BlackRock по токенизации",
            "entities": ("Ondo Finance", "BlackRock"),
            "first_seen": first + timedelta(minutes=2),
            "growth": 2,
            "current_channels": 2,
            "eligible": True,
        },
        {
            "story_id": "different-event",
            "title": "BlackRock and Ondo report quarterly earnings",
            "entities": ("Ondo Finance", "BlackRock"),
            "first_seen": first + timedelta(hours=1),
            "growth": 1,
            "current_channels": 2,
            "eligible": True,
        },
    ]
    selected, _ = select_agenda(cards, comparable_count=4)
    assert [item["story_id"] for item in selected] == ["portfolios", "different-event"]


def test_agenda_hides_overlapping_publication_for_same_close_entity_pair():
    from astrafeed.domain.agenda import select_agenda

    first = datetime(2026, 9, 24, 14, 19, tzinfo=UTC)
    cards = [
        {
            "story_id": "lawsuit",
            "title": "Штат Нью-Йорк подал иск против Polymarket",
            "entities": ("New York State", "Polymarket", "Bloomberg"),
            "first_seen": first,
            "source_signature": ("18:96927", "17:386238"),
            "growth": 3,
            "current_channels": 3,
            "eligible": True,
        },
        {
            "story_id": "illegal-gambling",
            "title": "Нью-Йорк подал в суд на Polymarket за незаконную игорную деятельность",
            "entities": ("New York State", "Polymarket", "Bloomberg"),
            "first_seen": first + timedelta(minutes=1),
            "source_signature": ("18:96927", "16:1044989"),
            "growth": 2,
            "current_channels": 2,
            "eligible": True,
        },
    ]
    selected, _ = select_agenda(cards, comparable_count=4)
    assert [item["story_id"] for item in selected] == ["lawsuit"]


def test_crypto_agenda_skips_story_without_market_anchor_in_displayed_evidence():
    from astrafeed.domain.agenda import select_agenda

    cards = [
        {
            "story_id": "medicare",
            "title": "OpenAI agent hacked Australia's Medicare portal",
            "entities": ("ETH", "FTX", "OpenAI", "Medicare"),
            "evidence_text": (
                "OpenAI agent hacked Australia's Medicare portal. "
                "Австралия заявляет, что агент OpenAI взломал портал Medicare."
            ),
            "growth": 3,
            "current_channels": 2,
            "eligible": True,
        },
        {
            "story_id": "payy",
            "title": "Payy, possibly hacked for $1.83 million",
            "evidence_text": (
                "Payy, possibly hacked for $1.83 million. "
                "Хакер взломал криптопроект Payy на $1,83m."
            ),
            "growth": 2,
            "current_channels": 2,
            "eligible": True,
        },
    ]
    selected, _ = select_agenda(cards, comparable_count=4)
    assert [item["story_id"] for item in selected] == ["payy"]
