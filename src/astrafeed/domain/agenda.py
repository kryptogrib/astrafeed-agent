"""AstraFeed agenda: publications, claims, stories, and comparable windows.

Four separate notions: entity (Ethereum), story (ETH ETF flows), event
(outflow on a date), position (author reads the outflow as weak demand).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

CLASSIFIER_VERSION = "open-extract/v1"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIM = 1536
EMBEDDING_PREP_VERSION = "fragment-entities/v1"
WINDOW = timedelta(hours=24)
LOOKBACK = timedelta(hours=48)
STALE_AFTER = timedelta(minutes=15)
AGENDA_LIMIT = 10
MIN_CHANNELS = 2
CANDIDATE_K = 10
SEARCH_DEFAULT_LIMIT = 10
SEARCH_MAX_LIMIT = 100

ClaimKind = Literal["event", "author_position", "explicit_call"]
Speaker = Literal["author", "quoted_participant", "unknown"]
MatchDecision = Literal["existing", "new", "ambiguous"]
ExtractionStatus = Literal["ok", "empty", "error"]
CyclePhase = Literal["idle", "collect", "analyze", "snapshot", "blocked"]

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_TODAY = re.compile(r"\bсегодня\b", re.IGNORECASE)
_YESTERDAY = re.compile(r"\bвчера\b", re.IGNORECASE)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def analysis_reuse_key(text_digest: str, classifier_version: str = CLASSIFIER_VERSION) -> str:
    return f"{text_digest}:{classifier_version}"


def embedding_cache_key(
    text: str,
    *,
    model: str = EMBEDDING_MODEL,
    prep_version: str = EMBEDDING_PREP_VERSION,
) -> str:
    payload = f"{model}\n{prep_version}\n{text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def publication_id(source_id: int, external_id: str) -> str:
    return f"{source_id}:{external_id}"


def resolve_quote_span(text: str, quote: str, start: object, end: object) -> tuple[int, int] | None:
    """Accept text[start:end]==quote, or a quote that occurs exactly once."""
    if not isinstance(quote, str) or not quote:
        return None
    if (
        isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start < end <= len(text)
        and text[start:end] == quote
    ):
        return start, end
    first = text.find(quote)
    if first < 0 or text.find(quote, first + 1) >= 0:
        return None
    return first, first + len(quote)


def numbers_in(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def numbers_are_grounded(paraphrase: str, quotes: list[str]) -> bool:
    allowed: set[str] = set()
    for quote in quotes:
        allowed |= numbers_in(quote)
    return numbers_in(paraphrase) <= allowed


def resolve_relative_when(value: str, published_at: datetime) -> str:
    day = published_at.date()
    if _TODAY.fullmatch(value.strip()):
        return day.isoformat()
    if _YESTERDAY.fullmatch(value.strip()):
        return (day - timedelta(days=1)).isoformat()
    return value


def windows_at(t: datetime) -> tuple[tuple[datetime, datetime], tuple[datetime, datetime]]:
    current = (t - WINDOW, t)
    previous = (t - LOOKBACK, t - WINDOW)
    return current, previous


def in_window(ts: datetime, window: tuple[datetime, datetime]) -> bool:
    start, end = window
    return start <= ts < end


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    na = sum(a * a for a in left) ** 0.5
    nb = sum(b * b for b in right) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def comparable_channel_ids(states: dict[int, dict[str, bool]]) -> frozenset[int]:
    return frozenset(
        source_id
        for source_id, state in states.items()
        if state.get("current_complete")
        and state.get("previous_complete")
        and state.get("processed")
    )


def decide_growth(
    *,
    current_channels: int,
    previous_channels: int,
    comparable_count: int,
    previous_window_complete: bool,
) -> tuple[int | None, str | None]:
    if comparable_count < MIN_CHANNELS or not previous_window_complete:
        return None, "comparable_channels_below_2"
    return current_channels - previous_channels, None


def agenda_rank_key(story: dict[str, Any]) -> tuple:
    growth = story.get("growth")
    growth_order = -(growth if isinstance(growth, int) else -(10**9))
    freshness = story.get("freshness")
    freshness_key = freshness.timestamp() if isinstance(freshness, datetime) else 0.0
    return (
        growth_order,
        -int(story.get("current_channels") or 0),
        -freshness_key,
        str(story.get("story_id") or ""),
    )


def rank_agenda_stories(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [s for s in stories if s.get("eligible")]
    return sorted(eligible, key=agenda_rank_key)


def select_agenda(
    cards: list[dict[str, Any]], comparable_count: int
) -> tuple[list[dict[str, Any]], str]:
    """Pick the published agenda and the honesty mode.

    Full compare with no new/growing stories → empty. Too few comparable
    channels → multi-channel stories without a growth claim.
    """
    multi = [
        c
        for c in cards
        if c.get("eligible", True) and int(c.get("current_channels") or 0) >= MIN_CHANNELS
    ]
    ranked = rank_agenda_stories([{**c, "eligible": True} for c in multi])
    def limit_entities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for item in items:
            entity = str(item.get("primary_entity") or "").casefold()
            if entity and counts.get(entity, 0) >= 2:
                continue
            selected.append(item)
            if entity:
                counts[entity] = counts.get(entity, 0) + 1
            if len(selected) == AGENDA_LIMIT:
                break
        return selected

    if comparable_count < MIN_CHANNELS:
        return limit_entities(ranked), "limited_no_growth_claim"
    growing = [c for c in ranked if isinstance(c.get("growth"), int) and c["growth"] > 0]
    if not growing:
        return [], "empty_no_growth"
    return limit_entities(growing), "full"


def is_stale(published_at: datetime, now: datetime) -> bool:
    return now - published_at >= STALE_AFTER


def queue_reason_retryable(reason: str) -> bool:
    head, sep, count = reason.rpartition(":")
    return not (sep and head.endswith("_error") and count.isdecimal() and int(count) >= 3)


def embedding_input(fragment_text: str, entity_surfaces: list[str]) -> str:
    names = ", ".join(surface for surface in entity_surfaces if surface.strip())
    if names:
        return f"{fragment_text}\nEntities: {names}"
    return fragment_text


def lexical_tokens(*parts: str) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        for token in re.findall(r"[0-9A-Za-zА-Яа-яЁё$]{2,}", part.casefold()):
            tokens.add(token)
    return tokens


@dataclass(frozen=True)
class PublicationVersion:
    publication_id: str
    source_id: int
    external_id: str
    text: str
    text_hash: str
    published_at: datetime
    detected_at: datetime
    channel_ref: str
    link: str
    version: int = 1


@dataclass(frozen=True)
class MentionedEntity:
    surface: str
    context: str


@dataclass(frozen=True)
class ExtractedNumber:
    value: str
    unit: str = ""


@dataclass(frozen=True)
class Claim:
    kind: ClaimKind
    speaker: Speaker
    quote: str
    start: int
    end: int
    is_ad: bool = False
    dates: tuple[str, ...] = ()
    numbers: tuple[ExtractedNumber, ...] = ()


@dataclass(frozen=True)
class Fragment:
    text: str
    start: int
    end: int
    is_ad: bool = False
    entities: tuple[MentionedEntity, ...] = ()
    claims: tuple[Claim, ...] = ()


@dataclass(frozen=True)
class ExtractionResult:
    reuse_key: str
    text_hash: str
    classifier_version: str
    status: ExtractionStatus
    fragments: tuple[Fragment, ...] = ()
    error: str = ""


@dataclass(frozen=True)
class Entity:
    entity_id: str
    canonical_name: str
    status: Literal["confirmed", "ambiguous"] = "confirmed"
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Story:
    story_id: str
    title_ru: str
    boundary: str
    first_seen: datetime
    key_entity: str = ""


@dataclass(frozen=True)
class Event:
    event_id: str
    story_id: str
    when: str
    amount: str = ""
    participants: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoryLink:
    story_id: str
    publication_id: str
    version: int
    fragment_index: int
    claim_index: int
    event_id: str | None = None
    entity_ids: tuple[str, ...] = ()
    kind: ClaimKind = "event"
    speaker: Speaker = "unknown"
    quote: str = ""
    paraphrase_ru: str = ""


@dataclass(frozen=True)
class ChannelWindowState:
    source_id: int
    current_complete: bool
    previous_complete: bool
    processed: bool
    current_empty_ok: bool = False
    previous_empty_ok: bool = False


@dataclass(frozen=True)
class CoverageInfo:
    channels_ok: int
    channels_failed: int
    channels_incomplete: int
    publications_total: int
    publications_processed: int
    publications_queued: int
    publications_failed: int
    comparable_channels: int
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimCard:
    kind: ClaimKind
    speaker: Speaker
    quote: str
    paraphrase_ru: str
    link: str
    channel_ref: str
    published_at: datetime


@dataclass(frozen=True)
class StoryCard:
    story_id: str
    title: str
    entities: tuple[str, ...]
    current_channels: int
    previous_channels: int | None
    growth: int | None
    growth_null_reason: str | None
    first_seen: datetime
    freshness: datetime
    explanation: str
    claims: tuple[ClaimCard, ...]
    publications: int = 0
    exact_repeats: int = 0
    retellings: int = 0
    event_count: int = 0
    position_count: int = 0


@dataclass(frozen=True)
class EventCard:
    event_id: str
    when: str
    amount: str
    participants: tuple[str, ...]
    quotes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PositionCard:
    speaker: Speaker
    channel_ref: str
    quote: str
    paraphrase_ru: str
    link: str


@dataclass(frozen=True)
class PublicationRef:
    publication_id: str
    channel_ref: str
    link: str
    published_at: datetime
    quote: str = ""


@dataclass(frozen=True)
class StoryDetail:
    card: StoryCard
    events: tuple[EventCard, ...] = ()
    positions: tuple[PositionCard, ...] = ()
    publications: tuple[PublicationRef, ...] = ()


@dataclass(frozen=True)
class SearchHit:
    story_id: str
    title: str
    matched: tuple[str, ...]
    score: float


@dataclass(frozen=True)
class SearchDoc:
    story_id: str
    kind: Literal["title", "entity", "alias", "claim", "publication"]
    text: str


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    t: datetime
    collected_at: datetime
    analyzed_at: datetime
    published_at: datetime
    coverage: CoverageInfo
    queue_depth: int
    limitations: tuple[str, ...]
    agenda: tuple[StoryCard, ...]
    agenda_mode: str
    stories: dict[str, StoryDetail] = field(default_factory=dict)
    search_docs: tuple[SearchDoc, ...] = ()


@dataclass
class CycleState:
    phase: CyclePhase = "idle"
    last_error: str = ""
    last_success_at: datetime | None = None
    last_collect_at: datetime | None = None
    last_partial_at: datetime | None = None
    last_full_success_at: datetime | None = None
    last_analyze_at: datetime | None = None
    budget_blocked: bool = False
    queue_depth: int = 0
    first_collect_done: bool = False


@dataclass(frozen=True)
class IndexedFragment:
    publication_id: str
    published_at: datetime
    fragment_index: int
    text: str
    entity_surfaces: tuple[str, ...]
    claim_text: str
    vector: list[float] | None = None
