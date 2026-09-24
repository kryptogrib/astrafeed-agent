"""Code-computed story signals: echoes, conflicting figures, sourcing, spread.

Everything here is deterministic over stored publication texts and times. A
signal describes what the observed posts say and when, never whether the story
is true: an "official" marker means a post cites an official statement.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from statistics import median
from typing import Protocol

from astrafeed.domain.agenda import (
    CaveatDrop,
    ChannelLead,
    FigureGroup,
    PriceMove,
    PublicationVersion,
    Snapshot,
    SourceNode,
    StoryCard,
    StorySignals,
)

_log = logging.getLogger(__name__)

# Two posts count as one voice when the later one repeats the earlier one this
# closely after links, mentions and emoji are stripped.
ECHO_SIMILARITY = 0.8
# Amounts closer than this share a group ("$100M" and "$100.5M" agree).
FIGURE_TOLERANCE = 0.1

_URL = re.compile(r"https?://\S+|t\.me/\S+|@\w+")
_NON_WORD = re.compile(r"[^\w$%.,]+", re.UNICODE)
_UNCERTAINTY = re.compile(
    r"\b(?:potentially|possibly|allegedly|unconfirmed|rumou?r(?:ed)?|возможно|вероятно|предположительно|якобы)\b",
    re.I,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")

_OFFICIAL = re.compile(
    r"официальн\w*|подтвердил\w*|объявил\w*|анонсировал\w*|сообщил\w* в (?:своём|своем|официальном)"
    r"|\bofficial(?:ly)?\b|\bconfirm(?:ed|s)\b|\bannounc(?:ed|es)\b|пресс-релиз|press release",
    re.I,
)
_ATTRIBUTED = re.compile(
    r"по данным|согласно|заявил\w*|сообщает|сообщили|пишет|источник[:и]|данные\s+\w+\s+показ\w+"
    r"|\baccording to\b|\breport(?:ed|s) by\b|\bper\b\s+[A-Z]|\bdata from\b|\bsource:",
    re.I,
)
_RUMOR = re.compile(
    r"слух\w*|вероятно|возможно|предположительно|якобы|не подтвержд\w*"
    r"|инсайд\w*|в твиттер\w* (?:пишут|сообщают)"
    r"|\bpotentially\b|\breportedly\b|\bunconfirmed\b|\brumou?r\w*\b"
    r"|\ballegedly\b|\bpossible\b|\bpossibly\b",
    re.I,
)
# On-chain analysts and wires often named as the origin of a figure.
_NAMED_SOURCES = (
    "Arkham",
    "Lookonchain",
    "PeckShield",
    "CertiK",
    "ZachXBT",
    "Cyvers",
    "SlowMist",
    "Whale Alert",
    "Glassnode",
    "CryptoQuant",
    "Santiment",
    "Farside",
    "SoSoValue",
    "Coinglass",
    "CoinGlass",
    "Nansen",
    "DefiLlama",
    "Bloomberg",
    "Reuters",
    "CoinDesk",
    "The Block",
    "Wu Blockchain",
    "WSJ",
    "Financial Times",
    "SEC",
    "Polymarket",
)

_SCHEDULED = re.compile(
    r"анонс данных|прогноз:|предыдущ\w*:|ожидается публикаци\w*|календар\w*"
    r"|\bPMI\b|\bCPI\b|\bPPI\b|\bNFP\b|\bGDP\b|interest rate decision|business climate"
    r"|unemployment rate|уровень безработицы|ставк\w+ (?:ФРС|ЕЦБ|SNB|ЦБ)|FOMC",
    re.I,
)

_MULT = {
    "k": 1e3,
    "тыс": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mn": 1e6,
    "mln": 1e6,
    "млн": 1e6,
    "million": 1e6,
    "b": 1e9,
    "bn": 1e9,
    "млрд": 1e9,
    "billion": 1e9,
}
_AMOUNT = re.compile(
    r"(?P<pre>\$\s?)?(?P<num>\d{1,3}(?:[ ,]\d{3})+|\d+(?:[.,]\d+)?)\s?"
    r"(?P<mult>тыс\.?|млн|млрд|mln|mn|bn|million|billion|thousand|[KkMmBb])?(?!\w)\+?\s?"
    r"(?P<post>\$|долл\w*|USD[TC]?\b|usd\b)?",
)
_TICKER = re.compile(r"(?:\$([A-Z][A-Z0-9]{1,9})\b|\(([A-Z][A-Z0-9]{1,9})\))")
_NAME_TICKERS = {
    "bitcoin": "BTC",
    "биткоин": "BTC",
    "биткойн": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "эфир": "ETH",
    "эфириум": "ETH",
    "eth": "ETH",
    "solana": "SOL",
    "солана": "SOL",
    "sol": "SOL",
    "hyperliquid": "HYPE",
    "hype": "HYPE",
    "bitget": "BGB",
    "binance": "BNB",
    "bnb": "BNB",
    "xrp": "XRP",
    "ripple": "XRP",
    "toncoin": "TON",
    "ton": "TON",
    "dogecoin": "DOGE",
    "doge": "DOGE",
    "ondo": "ONDO",
    "tron": "TRX",
    "chainlink": "LINK",
    "avalanche": "AVAX",
    "sui": "SUI",
    "aptos": "APT",
    "zcash": "ZEC",
    "zec": "ZEC",
    "okb": "OKB",
    "pepe": "PEPE",
}
# Tickers that are also common words or fiat; never priced.
_NOT_TICKERS = {"USD", "USDT", "USDC", "EUR", "RUB", "CEO", "ETF", "SEC", "AI", "NFT", "TVL", "APY"}


def _normalized(text: str) -> str:
    return " ".join(_NON_WORD.sub(" ", _URL.sub(" ", text.casefold())).split())


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    short, long = sorted((a, b), key=len)
    if len(short) >= 60 and short in long:
        return True
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    return matcher.quick_ratio() >= ECHO_SIMILARITY and matcher.ratio() >= ECHO_SIMILARITY


def sourcing(text: str) -> str:
    if _OFFICIAL.search(text):
        return "official"
    if _RUMOR.search(text):
        return "rumor"
    if _ATTRIBUTED.search(text) or any(name in text for name in _NAMED_SOURCES):
        return "attributed"
    return "unmarked"


def _caveat_drop(firsts: list[PublicationVersion]) -> CaveatDrop | None:
    """Find one narrowly evidenced wording change, without inferring event truth."""
    for index, before in enumerate(firsts):
        for sentence in _SENTENCE.split(before.text):
            marker = _UNCERTAINTY.search(sentence)
            if not marker or not 35 <= len(sentence) <= 280:
                continue
            core = _normalized(_UNCERTAINTY.sub(" ", sentence))
            for after in firsts[index + 1 :]:
                if sourcing(after.text) != "unmarked":
                    continue
                for later in _SENTENCE.split(after.text):
                    if not 30 <= len(later) <= 280 or _UNCERTAINTY.search(later):
                        continue
                    if (
                        SequenceMatcher(None, core, _normalized(later), autojunk=False).ratio()
                        < 0.92
                    ):
                        continue
                    return CaveatDrop(
                        qualifier=marker.group(),
                        before_channel=before.channel_ref,
                        before_link=before.link,
                        before_quote=sentence.strip(),
                        after_channel=after.channel_ref,
                        after_link=after.link,
                        after_quote=later.strip(),
                        minutes_later=int(
                            (after.published_at - before.published_at).total_seconds() // 60
                        ),
                    )
    return None


def is_scheduled(title: str, texts: Iterable[str]) -> bool:
    """A calendar item: a scheduled data release rather than a developing story."""
    if _SCHEDULED.search(title):
        return True
    texts = list(texts)
    return bool(texts) and sum(bool(_SCHEDULED.search(t)) for t in texts) * 2 > len(texts)


def usd_amounts(text: str) -> list[tuple[str, float]]:
    """Dollar amounts stated in a text, as (wording, value in USD)."""
    found: list[tuple[str, float]] = []
    for match in _AMOUNT.finditer(text):
        if not (match["pre"] or match["post"]):
            continue
        mult_key = (match["mult"] or "").rstrip(".").casefold()
        if not mult_key:
            continue
        raw = match["num"].replace(" ", "")
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw):
            raw = raw.replace(",", "")
        else:
            raw = raw.replace(",", ".")
        try:
            value = float(raw) * _MULT[mult_key]
        except (ValueError, KeyError):
            continue
        found.append((match.group(0).strip(), value))
    return found


def _figure_groups(quotes: list[tuple[str, str]]) -> tuple[tuple[FigureGroup, ...], bool]:
    """Group amounts per channel; conflict when channels state materially different sums.

    Each channel contributes one headline figure: the amount other channels
    also state when there is one (a post may append an unrelated "UPD" sum),
    otherwise its largest amount rather than a breakdown line.
    """
    stated: dict[str, list[tuple[str, float]]] = {}
    for channel, text in quotes:
        stated.setdefault(channel, []).extend(usd_amounts(text))

    def close(a: float, b: float) -> bool:
        return abs(a - b) <= FIGURE_TOLERANCE * max(a, b)

    def support(channel: str, value: float) -> int:
        return sum(
            any(close(value, other) for _, other in amounts)
            for name, amounts in stated.items()
            if name != channel
        )

    per_channel: dict[str, tuple[str, float]] = {}
    for channel, amounts in stated.items():
        if amounts:
            per_channel[channel] = max(
                amounts, key=lambda item: (support(channel, item[1]), item[1])
            )
    groups: list[list] = []
    for channel, (wording, value) in per_channel.items():
        for group in groups:
            if abs(group[1] - value) <= FIGURE_TOLERANCE * max(group[1], value):
                group[2].append(channel)
                break
        else:
            groups.append([wording, value, [channel]])
    groups.sort(key=lambda g: (-len(g[2]), -g[1]))
    result = tuple(FigureGroup(text=g[0], usd=g[1], channels=tuple(g[2])) for g in groups)
    return result, len(result) >= 2


def tickers(title: str, entities: Iterable[str], texts: Iterable[str]) -> tuple[str, ...]:
    """Tradable tickers named by the story: explicit $TICKER/(TICKER) or a known project name.

    Only the title and quotes count: merged entity lists can carry names from
    unrelated posts, and a price must follow what the story actually says.
    """
    texts = list(texts)
    found: list[str] = []
    for source in (title, *texts):
        for match in _TICKER.finditer(source):
            symbol = match.group(1) or match.group(2)
            if symbol not in _NOT_TICKERS and symbol not in found:
                found.append(symbol)
    for name in (title, *texts):
        for word in re.findall(r"[\w$]+", name.casefold()):
            symbol = _NAME_TICKERS.get(word.lstrip("$"))
            if symbol and symbol not in found:
                found.append(symbol)
    return tuple(found[:3])


def story_signals(
    card: StoryCard,
    pubs: list[PublicationVersion],
    quotes: list[tuple[str, str]],
) -> StorySignals:
    """Signals for one story from its current-window posts and linked quotes.

    ``quotes`` pairs each linked quote with its channel; figures come only from
    those quotes so every compared amount is published evidence.
    """
    ordered = sorted(pubs, key=lambda pub: (pub.published_at, pub.publication_id))
    first_by_channel: dict[str, PublicationVersion] = {}
    for pub in ordered:
        first_by_channel.setdefault(pub.channel_ref, pub)
    firsts = list(first_by_channel.values())
    start = firsts[0].published_at if firsts else None
    nodes: list[SourceNode] = []
    normalized: list[tuple[str, str]] = []
    for pub in firsts:
        text = _normalized(pub.text)
        echo_of = next((channel for channel, prior in normalized if _similar(text, prior)), "")
        normalized.append((pub.channel_ref, text))
        nodes.append(
            SourceNode(
                channel_ref=pub.channel_ref,
                link=pub.link,
                published_at=pub.published_at,
                minutes_after_first=int((pub.published_at - start).total_seconds() // 60)
                if start
                else 0,
                echo_of=echo_of,
                sourcing=sourcing(pub.text),
            )
        )
    originals = [node for node in nodes if not node.echo_of]
    levels = [node.sourcing for node in originals]
    confirmation = next(
        (level for level in ("official", "attributed", "rumor") if level in levels), "unmarked"
    )
    joined = "\n".join(pub.text for pub in firsts)
    figures, conflict = _figure_groups(quotes)
    texts = [pub.text for pub in firsts]
    return StorySignals(
        sources=tuple(nodes),
        independent_channels=len(originals),
        echo_channels=len(nodes) - len(originals),
        spread_minutes=nodes[-1].minutes_after_first if len(nodes) >= 2 else None,
        confirmation=confirmation,
        attributed_to=tuple(name for name in _NAMED_SOURCES if name in joined)[:4],
        figures=figures,
        figures_conflict=conflict,
        tickers=tickers(card.title, card.entities, [q for _, q in quotes]),
        scheduled=is_scheduled(card.title, texts),
        caveat_drop=_caveat_drop(firsts),
    )


def lead_channels(cards: Iterable[StoryCard], limit: int = 5) -> tuple[ChannelLead, ...]:
    """Channels that most often posted a displayed story first, with their head start.

    The lead is the gap to the next independent channel; echoes do not count as
    being beaten, since a copy is not a separate report.
    """
    leads: dict[str, list[int]] = {}
    for card in cards:
        signals = card.signals
        if signals is None:
            continue
        originals = [node for node in signals.sources if not node.echo_of]
        if len(originals) < 2:
            continue
        leads.setdefault(originals[0].channel_ref, []).append(originals[1].minutes_after_first)
    ranked = sorted(leads.items(), key=lambda item: (-len(item[1]), -median(item[1]), item[0]))
    return tuple(
        ChannelLead(
            channel_ref=channel,
            stories_first=len(gaps),
            median_lead_minutes=int(median(gaps)),
        )
        for channel, gaps in ranked[:limit]
    )


def first_seen_at(signals: StorySignals | None, fallback: datetime) -> datetime:
    return signals.sources[0].published_at if signals and signals.sources else fallback


class MarketPrices(Protocol):
    async def last(self, inst_id: str) -> float | None: ...

    async def open_at(self, inst_id: str, at: datetime) -> float | None: ...


_MATERIAL_MOVE_PCT = 2.0
_SMALL_MOVE_PCT = 1.0


def price_timing_verdict(change_pct_before: float | None, change_pct_after: float) -> str | None:
    """Classify whether the market moved before the first observed Telegram post.

    Thresholds are magnitudes, not proof of a leak or of Telegram causing the move:
    2% counts as material, under 1% as quiet. Tune here if the report feels jumpy.
    """
    if change_pct_before is None:
        return None
    before, after = abs(change_pct_before), abs(change_pct_after)
    if before >= _MATERIAL_MOVE_PCT and after < _SMALL_MOVE_PCT:
        return "priced_in"
    if before < _SMALL_MOVE_PCT and after >= _MATERIAL_MOVE_PCT:
        return "telegram_ahead"
    if before >= _MATERIAL_MOVE_PCT and after >= _MATERIAL_MOVE_PCT:
        return "both_moved"
    return "quiet"


def _pct_change(start: float, end: float) -> float | None:
    if not start:
        return None
    return round((end - start) / start * 100, 2)


async def _price_move(
    market: MarketPrices, symbol: str, since: datetime, now: datetime
) -> PriceMove | None:
    inst_id = f"{symbol}-USDT"
    hour_before = since - timedelta(hours=1)
    before, then, last = await asyncio.gather(
        market.open_at(inst_id, hour_before),
        market.open_at(inst_id, since),
        market.last(inst_id),
    )
    if not then or not last:
        return None
    change_after = _pct_change(then, last)
    if change_after is None:
        return None
    change_before = _pct_change(before, then) if before else None
    return PriceMove(
        inst_id=inst_id,
        since=since,
        price_then=then,
        price_now=last,
        change_pct=change_after,
        measured_at=now,
        price_hour_before=before,
        change_pct_before=change_before,
        verdict=price_timing_verdict(change_before, change_after),
    )


async def add_price_moves(
    snapshot: Snapshot, market: MarketPrices, now: datetime, *, timeout_seconds: float = 20
) -> Snapshot:
    """Attach OKX spot price change since each story's first observed post.

    Price data is context, not causation. Any failure leaves the card without a price.
    """

    async def one(card: StoryCard) -> StoryCard:
        signals = card.signals
        if signals is None or not signals.tickers or not signals.sources:
            return card
        since = signals.sources[0].published_at
        for symbol in signals.tickers:
            try:
                move = await _price_move(market, symbol, since, now)
            except Exception as exc:  # network, JSON, rate limit
                _log.warning("price lookup %s failed: %s", symbol, type(exc).__name__)
                continue
            if move is not None:
                return replace(card, signals=replace(signals, price=move))
        return card

    try:
        async with asyncio.timeout(timeout_seconds):
            agenda = tuple(await asyncio.gather(*(one(card) for card in snapshot.agenda)))
    except TimeoutError:
        _log.warning("price lookup timed out")
        return snapshot
    stories = dict(snapshot.stories)
    for card in agenda:
        detail = stories.get(card.story_id)
        if detail is not None:
            stories[card.story_id] = replace(
                detail, card=replace(detail.card, signals=card.signals)
            )
    return replace(snapshot, agenda=agenda, stories=stories)
