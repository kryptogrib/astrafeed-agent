from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Route(str, Enum):
    REPORT = "report"
    DROP = "drop"


class InterestScope(str, Enum):
    GLOBAL = "global"
    GROUP = "group"
    CHANNEL = "channel"


class InterestMode(str, Enum):
    EXTEND = "extend"
    REPLACE = "replace"


class MatchType(str, Enum):
    LITERAL = "literal"
    REGEX = "regex"


@dataclass(frozen=True)
class KeywordRule:
    """A global keyword Alert rule. `literal` rules substring-match; `regex`
    rules use `re.search`. `ignore_case` case-folds both sides (literal) or
    sets re.IGNORECASE (regex). Disabled rules are persisted but skipped by
    the matcher. The pure matcher lives in `astrafeed.domain.keywords`."""

    pattern: str
    match_type: MatchType
    enabled: bool = True
    ignore_case: bool = True
    id: int | None = None


@dataclass(frozen=True)
class Interest:
    text: str
    scope: InterestScope = InterestScope.GLOBAL
    id: int | None = None
    # Scope owner: group/channel id, or None for this user's global interests.
    # Not the tenant user — that lives on the storage row as a separate user_id.
    owner_id: int | None = None


@dataclass(frozen=True)
class Group:
    name: str
    id: int | None = None
    interest_mode: InterestMode = InterestMode.EXTEND


@dataclass(frozen=True)
class Channel:
    telegram_ref: str
    name: str
    id: int | None = None
    group_id: int | None = None
    interest_mode: InterestMode = InterestMode.EXTEND
    # Two orthogonal flags decouple Report inclusion from Alert monitoring.
    # A channel is fetched iff include_in_report or include_in_alerts
    # ("monitored at all" is derived, not stored).
    include_in_report: bool = True
    include_in_alerts: bool = True
    # When True the channel is an aggregator that re-forwards many others;
    # Source Lead mining is suppressed entirely for it (see _mine_leads).
    is_aggregator: bool = False
    removed_at: datetime | None = None
    # Nullable until the public source is resolved (task 06). Catalog membership
    # is not an access grant: a stored public source_id is not a right to a
    # private channel. Personal uniqueness stays (user_id, telegram_ref).
    source_id: int | None = None


@dataclass(frozen=True)
class Item:
    channel_ref: str
    external_id: str
    text: str
    link: str
    timestamp: datetime
    has_media: bool = False
    # Set when the message is a forward whose origin is a public channel;
    # drives Source Lead extraction. Persisted in the shared IngestionStore
    # raw cache (and research snapshots); not on the personal report queue.
    forwarded_from_ref: str | None = None
    forwarded_from_title: str | None = None
    # Human-readable name of the source channel, used as the report source
    # label when the channel has no public @handle (private id:).
    channel_name: str | None = None


@dataclass(frozen=True)
class DiscussionComment:
    external_id: str
    text: str
    timestamp: datetime
    link: str = ""
    # Technical, source-internal identifier for the comment's author (NOT a
    # display name, NOT a notion of expertise/reputation) — used only to tell
    # "same author" from "different author" apart. Optional/defaulted so old
    # JSONL cache records (written before this field existed) still load.
    author_key: str | None = None
    # ID of the comment this one directly replies to (its parent), if known.
    reply_to_id: str | None = None
    # Last-edit timestamp, if the source reports one.
    edited_at: datetime | None = None
    peer_id: str | None = None
    thread_root_id: str | None = None
    parent_peer_id: str | None = None
    has_media: bool = False


class CommentStatus(str, Enum):
    """Why a discussion fetch returned the comments it did.

    Distinguishing these is what lets an offline cache avoid recording a
    transient failure (flood-wait, error) as the stable truth "no comments".
    ``EMPTY`` means the thread was reachable and genuinely had nothing;
    ``UNAVAILABLE`` means there is no linked/visible discussion to read.
    """

    FETCHED = "fetched"  # >= 1 comment read
    EMPTY = "empty"  # discussion reachable, zero replies
    UNAVAILABLE = "unavailable"  # no linked discussion / not accessible
    FLOOD_WAIT = "flood_wait"  # rate-limited; retryable
    ERROR = "error"  # unexpected failure; retryable


@dataclass(frozen=True)
class CommentFetch:
    """Outcome of fetching discussion comments for a single Item.

    ``raw_count`` is the number of replies seen before any model-free gating, and
    ``limit`` is the cap the fetch was asked for — both persisted so a cache built
    at a smaller ``limit`` can be detected and re-fetched instead of silently
    under-enriching.
    """

    status: CommentStatus
    comments: tuple[DiscussionComment, ...] = ()
    raw_count: int = 0
    limit: int = 0
    # Human-readable note on *why* a non-FETCHED status happened (e.g. the
    # Telethon error text for UNAVAILABLE/ERROR/FLOOD_WAIT). Persisted into the
    # comments cache so a record explains itself without cross-referencing trace.log.
    reason: str = ""
    # True when parent-fetching (backfilling comments referenced via
    # ``reply_to_id`` but missing from ``comments``) failed or was incomplete.
    # A failed parent fetch must never be silently read as "parent doesn't
    # exist" — it sets this flag and records the id in ``missing_parent_ids``.
    context_incomplete: bool = False
    # True when collection hit a cap (the main-comment limit or the parent
    # backfill budget) without the source reporting a definitive "that's
    # everything" signal — so thread completeness is not guaranteed even
    # though no error occurred.
    possibly_truncated: bool = False
    # IDs of parent comments that were referenced (via ``reply_to_id``) but
    # could not be fetched.
    missing_parent_ids: tuple[str, ...] = ()
    discussion_peer_id: str | None = None
    root_id: str | None = None
    parent_issues: tuple[tuple[str, str], ...] = ()
    collection_stop_reason: str = ""


@dataclass(frozen=True)
class Verdict:
    item: Item
    route: Route
    matched_interests: tuple[str, ...] = ()
    rationale: str = ""
    summary: str = ""
    importance: int = 1  # 1..5, set by the cheap model; drives Report ranking
    new_fact: str = ""
    evidence: str = ""
    # Normalized "actor|action|object" naming the event this item reports. Filled
    # by the scorer, used by report dedup to recognise a rewrite of the same news.
    event_key: str = ""
    # Semantic urgency is independent of keyword Alerts and of Importance.
    # Defaults keep old queue rows and scorer replies non-urgent.
    urgent_candidate: bool = False
    urgent_interest: str = ""
    urgent_reason: str = ""
    # Best-effort audit identity; nullable so an audit outage never blocks queueing.
    provenance_id: str | None = None


@dataclass(frozen=True)
class Subscription:
    """A channel the Telegram account is subscribed to, surfaced for selection.

    `monitored` is filled by the use-case layer (True when this subscription is
    already an enabled Channel in the repository)."""

    telegram_ref: str
    title: str
    telegram_id: int | None = None
    monitored: bool = False
    # "channel" for broadcast channels, "chat" for supergroups/megagroups.
    kind: str = "channel"


@dataclass(frozen=True)
class LeadObservation:
    """A single sighting of a Source Lead, fed to ``record_source_leads``.

    ``ref`` arrives already normalized/lower-cased from ``extract_source_leads``;
    ``source_ref`` is the channel the lead was seen in (defensively lower-cased
    by the repo for case-insensitive dedup of ``source_refs``)."""

    ref: str
    source_ref: str
    title: str | None
    item_link: str


@dataclass(frozen=True)
class SourceLead:
    """Aggregate read model of a Source Lead (one per normalized ``ref``).

    Selection/cooldown is not modelled here — this is the raw stored row.
    ``source_refs`` holds at most 3 distinct channels the lead was seen in."""

    ref: str
    times_seen: int
    first_seen_at: datetime
    last_seen_at: datetime
    last_shown_at: datetime | None = None
    times_seen_at_last_show: int = 0
    status: str = "new"
    title: str | None = None
    source_refs: tuple[str, ...] = ()
    last_item_link: str = ""


@dataclass(frozen=True)
class CostEntry:
    model: str
    stage: str  # "score" | "compose_report"
    input_tokens: int
    output_tokens: int
    cost: float | None  # None: provider did not report the charged amount
    latency_ms: int
    decision: str = ""
    channel_id: int | None = None
    recorded_at: datetime | None = None
    execution_id: str | None = None
    logical_call_id: str | None = None
