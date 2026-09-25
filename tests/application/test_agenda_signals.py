from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.application.agenda_signals import (
    _figure_groups,
    add_price_moves,
    is_scheduled,
    lead_channels,
    move_done_pct,
    price_timing_verdict,
    sourcing,
    story_signals,
    tickers,
    usd_amounts,
)
from astrafeed.domain.agenda import (
    CoverageInfo,
    PublicationVersion,
    Snapshot,
    StoryCard,
)

T0 = datetime(2026, 9, 24, 7, 30, tzinfo=UTC)


def _pub(channel: str, text: str, minutes: int, n: int = 1) -> PublicationVersion:
    return PublicationVersion(
        publication_id=f"{channel}:{n}",
        source_id=hash(channel) % 1000,
        external_id=str(n),
        text=text,
        text_hash=str(hash(text)),
        published_at=T0 + timedelta(minutes=minutes),
        detected_at=T0,
        channel_ref=channel,
        link=f"https://t.me/{channel.lstrip('@')}/{n}",
    )


def _card(title: str = "Bitget hack", entities: tuple[str, ...] = ("Bitget",)) -> StoryCard:
    return StoryCard(
        story_id="st-1",
        title=title,
        entities=entities,
        current_channels=3,
        previous_channels=0,
        growth=3,
        growth_null_reason=None,
        first_seen=T0,
        freshness=T0,
        explanation="",
        claims=(),
    )


HACK = "Биржа Bitget взломана, похищено более $100 млн. Команда расследует инцидент."


def test_near_verbatim_copy_is_an_echo_not_an_independent_channel():
    pubs = [
        _pub("@marketfeed", HACK, 0),
        _pub("@aggregator", HACK + " 👉 t.me/aggregator", 4),
        _pub("@markettwits", "По данным Arkham, из Bitget вывели $180M", 25),
    ]
    signals = story_signals(_card(), pubs, [])
    assert [node.echo_of for node in signals.sources] == ["", "@marketfeed", ""]
    assert (signals.independent_channels, signals.echo_channels) == (2, 1)
    assert signals.spread_minutes == 25


def test_later_retelling_drops_explicit_uncertainty_with_linked_wording():
    earlier = _pub("@first", "POTENTIALLY: Bitget wallets were hacked and $100M was withdrawn.", 0)
    later = _pub("@later", "Bitget wallets were hacked and $100M was withdrawn.", 4)
    signals = story_signals(_card(), [earlier, later], [])
    assert signals.caveat_drop is not None
    assert signals.caveat_drop.qualifier == "POTENTIALLY"
    assert signals.caveat_drop.before_channel == "@first"
    assert signals.caveat_drop.after_channel == "@later"
    assert signals.caveat_drop.before_link == earlier.link
    assert signals.caveat_drop.after_link == later.link
    assert signals.caveat_drop.minutes_later == 4


def test_caveat_drop_requires_close_wording_and_no_later_sourcing():
    earlier = _pub("@first", "Possibly Bitget wallets were hacked and $100M was withdrawn.", 0)
    different = _pub("@other", "Bitget deposits resume after a maintenance window.", 4)
    attributed = _pub(
        "@later", "According to Arkham, Bitget wallets were hacked and $100M was withdrawn.", 5
    )
    assert story_signals(_card(), [earlier, different, attributed], []).caveat_drop is None
    assert (
        story_signals(_card(), [earlier, _pub("@later", earlier.text, 5)], []).caveat_drop is None
    )


def test_caveat_drop_is_visible_with_both_evidence_links():
    from dataclasses import replace

    from astrafeed.application.agenda_query import _card_payload, _html_card_head, _md_card_head

    before = _pub("@first", "POTENTIALLY: Bitget wallets were hacked and $100M was withdrawn.", 0)
    after = _pub("@later", "Bitget wallets were hacked and $100M was withdrawn.", 4)
    card = _card()
    payload = _card_payload(replace(card, signals=story_signals(card, [before, after], [])))
    shift = payload["signals"]["caveat_drop"]
    assert (shift["before_link"], shift["after_link"]) == (before.link, after.link)
    md = "\n".join(_md_card_head(payload, "## Bitget"))
    html = _html_card_head(payload, "<h2>Bitget</h2>")
    assert "Qualifier dropped" in md and before.link in md and after.link in md
    assert "Qualifier dropped" in html and before.link in html and after.link in html


def test_channels_stating_different_amounts_are_flagged():
    quotes = [
        ("@marketfeed", "похищено более $100 млн"),
        ("@cryptoattack24", "ущерб >100 млн $"),
        ("@markettwits", "вывели $180M"),
    ]
    signals = story_signals(_card(), [], quotes)
    assert signals.figures_conflict
    assert [len(f.channels) for f in signals.figures] == [2, 1]
    assert [f.usd for f in signals.figures] == [100e6, 180e6]


def test_close_amounts_agree():
    signals = story_signals(_card(), [], [("@a", "$100M"), ("@b", "$102 млн")])
    assert not signals.figures_conflict


def test_amounts_need_currency_and_scale():
    assert usd_amounts("2 млн пользователей и 30 монет") == []
    assert usd_amounts("$1,83 млн") == [("$1,83 млн", 1.83e6)]
    assert usd_amounts("raised $12.5B") == [("$12.5B", 12.5e9)]


@pytest.mark.parametrize(
    ("text", "level"),
    [
        ("Bitget официально подтвердила взлом", "official"),
        ("POTENTIALLY: Bitget hacked", "rumor"),
        ("По данным Arkham, выведено $180M", "attributed"),
        ("Lookonchain: whale bought 10k ETH", "attributed"),
        ("Биткоин растёт", "unmarked"),
    ],
)
def test_sourcing_levels(text, level):
    assert sourcing(text) == level


def test_macro_calendar_item_is_scheduled():
    assert is_scheduled("Ifo Business Climate Index: анонс данных", [])
    assert not is_scheduled("Binance lists Hyperliquid (HYPE)", ["Binance листит HYPE"])


def test_tickers_from_symbols_and_known_names():
    signals = story_signals(
        _card("Binance lists Hyperliquid (HYPE)", ("Binance", "Hyperliquid")), [], []
    )
    assert signals.tickers[0] == "HYPE"
    assert "BNB" in signals.tickers


def test_lead_channels_ignore_copies():
    pubs = [
        _pub("@fast", HACK, 0),
        _pub("@copycat", HACK, 1),
        _pub("@slow", "Bitget сообщила о взломе кошелька", 30),
    ]
    from dataclasses import replace

    card = replace(_card(), signals=story_signals(_card(), pubs, []))
    (lead,) = lead_channels([card])
    assert (lead.channel_ref, lead.median_lead_minutes) == ("@fast", 30)


class _Market:
    def __init__(
        self, fail: bool = False, opens: dict[datetime, float] | None = None, last: float = 110.0
    ) -> None:
        self.fail = fail
        self.opens = opens
        self.last_price = last
        self.asked: list[datetime] = []

    async def last(self, inst_id: str) -> float | None:
        if self.fail:
            raise RuntimeError("down")
        return self.last_price if inst_id == "HYPE-USDT" else None

    async def open_at(self, inst_id: str, at: datetime) -> float | None:
        if self.fail:
            raise RuntimeError("down")
        self.asked.append(at)
        if inst_id != "HYPE-USDT":
            return None
        if self.opens is not None:
            return self.opens.get(at)
        return 100.0


def _snapshot(card: StoryCard) -> Snapshot:
    coverage = CoverageInfo(0, 0, 0, 0, 0, 0, 0, 0)
    return Snapshot("s", T0, T0, T0, T0, coverage, 0, (), (card,), "full")


async def test_price_move_since_first_post():
    card = _card("Binance lists Hyperliquid (HYPE)", ("Hyperliquid",))
    from dataclasses import replace

    card = replace(card, signals=story_signals(card, [_pub("@a", "HYPE listing", 0)], []))
    out = await add_price_moves(_snapshot(card), _Market(), T0 + timedelta(hours=3))
    price = out.agenda[0].signals.price
    assert (price.inst_id, price.change_pct, price.since) == ("HYPE-USDT", 10.0, T0)


async def test_price_failure_leaves_card_without_price():
    card = _card("Binance lists Hyperliquid (HYPE)", ("Hyperliquid",))
    from dataclasses import replace

    card = replace(card, signals=story_signals(card, [_pub("@a", "HYPE listing", 0)], []))
    out = await add_price_moves(_snapshot(card), _Market(fail=True), T0)
    assert out.agenda[0].signals.price is None


def test_price_timing_verdict_uses_the_reviewer_examples():
    assert price_timing_verdict(4.1, 0.3) == "priced_in"
    assert price_timing_verdict(0.0, 6.0) == "telegram_ahead"
    assert price_timing_verdict(3.0, 4.0) == "both_moved"
    assert price_timing_verdict(0.2, 0.4) == "quiet"
    assert price_timing_verdict(None, 6.0) is None


async def test_price_includes_the_hour_before_the_first_post():
    card = _card("Binance lists Hyperliquid (HYPE)", ("Hyperliquid",))
    from dataclasses import replace

    card = replace(card, signals=story_signals(card, [_pub("@a", "HYPE listing", 0)], []))
    hour_before = T0 - timedelta(hours=1)
    market = _Market(opens={hour_before: 96.0, T0: 100.0}, last=100.3)
    out = await add_price_moves(_snapshot(card), market, T0 + timedelta(hours=3))
    price = out.agenda[0].signals.price
    assert hour_before in market.asked
    assert price.price_hour_before == 96.0
    assert price.change_pct_before == 4.17
    assert price.change_pct == 0.3
    assert price.verdict == "priced_in"


def test_unrelated_update_amount_does_not_create_conflict() -> None:
    groups, conflict = _figure_groups(
        [
            ("@a", "Payy hacked for $1.83m. UPD: Duelbits also hacked for $4.3m."),
            ("@b", "Payy, possibly hacked for $1.83M"),
        ]
    )
    assert not conflict
    assert groups[0].channels == ("@a", "@b")


def test_entities_alone_do_not_add_a_ticker() -> None:
    assert (
        tickers(
            "Australia says an OpenAI agent hacked the Medicare portal",
            ["OpenAI", "ETH", "FTX"],
            ["Австралия заявляет, что агент OpenAI взломал портал Medicare"],
        )
        == ()
    )


async def test_each_original_source_shows_how_much_of_the_move_it_trailed():
    # Shape of live ONDO (snap-20260925T075313Z): the market moved before Telegram,
    # and the official post arrived after most of the move.
    card = _card("Binance lists Hyperliquid (HYPE)", ("Hyperliquid",))
    from dataclasses import replace

    pubs = [
        _pub("@first", "HYPE listing announced", 0),
        _pub("@copy", "HYPE listing announced", 5),
        _pub("@late", "Hyperliquid HYPE gets a Binance listing today", 120),
        _pub("@official", "Official: Binance will list HYPE", 600),
    ]
    card = replace(card, signals=story_signals(card, pubs, []))
    hour_before = T0 - timedelta(hours=1)
    opens = {
        hour_before: 100.0,
        T0: 104.0,
        T0 + timedelta(minutes=120): 110.0,
        T0 + timedelta(minutes=600): 118.0,
    }
    out = await add_price_moves(_snapshot(card), _Market(opens=opens, last=120.0), T0)
    points = out.agenda[0].signals.price.at_posts
    assert [(p.channel_ref, p.price, p.move_done_pct) for p in points] == [
        ("@first", 104.0, 20),
        ("@late", 110.0, 50),
        ("@official", 118.0, 90),
    ]


def test_move_done_is_unknown_for_a_quiet_market_and_clamped_on_overshoot():
    assert move_done_pct(100.0, 100.4, 100.5) is None
    assert move_done_pct(100.0, 125.0, 120.0) == 100
    assert move_done_pct(100.0, 97.0, 120.0) == 0
    assert move_done_pct(100.0, 90.0, 80.0) == 50


async def test_the_official_source_is_priced_even_when_it_posts_last():
    card = _card("Binance lists Hyperliquid (HYPE)", ("Hyperliquid",))
    from dataclasses import replace

    texts = [
        "HYPE may get listed soon",
        "Rumours say Hyperliquid token lands on a big exchange",
        "Traders expect a HYPE listing this week",
        "Is HYPE about to hit Binance?",
        "Insiders hint Hyperliquid will trade on Binance",
        "Hyperliquid listing chatter grows",
        "Everyone is talking about HYPE on Binance",
    ]
    pubs = [_pub(f"@c{n}", text, n * 30) for n, text in enumerate(texts)]
    pubs.append(_pub("@exchange", "Official announcement: Binance will list HYPE", 900))
    card = replace(card, signals=story_signals(card, pubs, []))
    out = await add_price_moves(_snapshot(card), _Market(), T0)
    channels = [p.channel_ref for p in out.agenda[0].signals.price.at_posts]
    assert channels[-1] == "@exchange"
    assert len(channels) == 6


def test_report_shows_the_price_trail_and_the_wait_for_an_official_statement():
    from astrafeed.application.agenda_query import _signal_lines

    def node(channel: str, minutes: int, sourcing: str = "unmarked") -> dict:
        return {"channel": channel, "minutes_after_first": minutes, "sourcing": sourcing}

    def point(channel: str, done: int | None) -> dict:
        return {"channel": channel, "move_done_pct": done}

    signals = {
        "confirmation": "official",
        "attributed_to": [],
        "sources": [node("@a", 0), node("@b", 60), node("@c", 1134, "official")],
        "spread_minutes": None,
        "figures_conflict": False,
        "official_after_minutes": 1134,
        "price": {
            "inst_id": "ONDO-USDT",
            "change_pct": 25.27,
            "price_then": 0.4516,
            "price_now": 0.5657,
            "at_posts": [point("@a", 18), point("@b", 45), point("@c", 86)],
        },
    }
    lines = _signal_lines({"signals": signals})
    assert "🕰 First post citing an official statement: 18h 54m after the first post" in lines
    assert lines[-1].endswith("@a 18% · @b 45% · @c 86%")

    signals["price"]["at_posts"] = [point("@a", None), point("@c", None)]
    assert not any(line.startswith("⏳") for line in _signal_lines({"signals": signals}))
