from datetime import UTC, datetime, timedelta

import pytest

from astrafeed.application.agenda_signals import (
    _figure_groups,
    add_price_moves,
    is_scheduled,
    lead_channels,
    sourcing,
    story_signals,
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
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def last(self, inst_id: str) -> float | None:
        if self.fail:
            raise RuntimeError("down")
        return 110.0 if inst_id == "HYPE-USDT" else None

    async def open_at(self, inst_id: str, at: datetime) -> float | None:
        return 100.0 if inst_id == "HYPE-USDT" else None


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


def test_unrelated_update_amount_does_not_create_conflict() -> None:
    groups, conflict = _figure_groups(
        [
            ("@a", "Payy hacked for $1.83m. UPD: Duelbits also hacked for $4.3m."),
            ("@b", "Payy, possibly hacked for $1.83M"),
        ]
    )
    assert not conflict
    assert groups[0].channels == ("@a", "@b")
