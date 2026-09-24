"""Event grouping without embeddings: exact dups, retellings, no ticker-only or transitive merge."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlsplit

from news_pulse_classify import TICKERS, Observation
from news_pulse_load import fold

TICKER_LIKE = re.compile(r"^(?:\$|#)?[a-z]{2,6}$")
DURATION_RE = re.compile(r"\b(\d+)\s*(?:sec|secs|seconds|s|сек|секунд)\b")
VERSION_RE = re.compile(r"\b(nu\s*\d+|v\d+(?:\.\d+)?)\b")
MONTH = (
    r"январ\w*|феврал\w*|март\w*|апрел\w*|ма[йя]\w*|июн\w*|июл\w*|август\w*|"
    r"сентябр\w*|октябр\w*|ноябр\w*|декабр\w*|january|february|march|april|may|"
    r"june|july|august|september|october|november|december"
)
DATE_RE = re.compile(rf"\b(\d{{1,2}})\s+({MONTH})\b")
AMOUNT_RE = re.compile(
    r"\$\s*(\d[\d\s.,]{0,14}\d|\d)\s*(млрд|млн|тыс|bn|b|m|k|million|billion)?(?![a-zа-я])"
    r"|(\d[\d\s.,]{0,14}\d|\d)\s*(млрд|млн|тыс|bn|million|billion)\.?\s*\$?"
)
ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})")
RELATIVE_DAYS = {"вчера": -1, "yesterday": -1, "сегодня": 0, "today": 0, "завтра": 1, "tomorrow": 1}
MONTH_NUM = {
    **{m: i for i, m in enumerate(
        ("январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"), 1)},
    **{m: i for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)},
}
SCALE_MUSD = {"млрд": 1000.0, "bn": 1000.0, "b": 1000.0, "billion": 1000.0, "млн": 1.0, "m": 1.0,
              "million": 1.0, "тыс": 0.001, "k": 0.001}

ACTION_ALIASES: dict[str, tuple[str, ...]] = {
    "vote": (
        "vote", "voted", "voting", "проголосова", "голосован", "поддержал",
        "supported", "support", "одобр", "approve", "approved",
    ),
    "reduce": ("reduce", "reduction", "сокращен", "ускор", "faster", "accelerate", "speed"),
    "upgrade": ("upgrade", "обновл", "planned", "планир", "targets", "запланирова"),
    "withdraw": ("withdraw", "вывел", "вывод", "transfer", "перевел"),
    "mint": ("mint", "минт"),
    "inflow": ("inflow", "приток"),
    "outflow": ("outflow", "отток"),
    "list": ("listing", "листинг", "list"),
    "launch": ("launch", "запуск"),
}

OBJECT_ALIASES: dict[str, tuple[str, ...]] = {
    "block_time": ("block time", "время блока", "формирован", "блоков", "blocks", "block"),
    "etf": ("etf",),
    "nu7": ("nu7", "nu 7"),
    "zec": ("zec", "zcash", "зкеш"),
    "eth": ("eth", "ethereum", "эфир"),
}

ACTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "zcash_community": ("zcash community", "сообщество zcash", "сообщество zec"),
    "zcash": ("zcash", "zec"),
    "community": ("community", "сборщ", "сообщество"),
}


@dataclass
class EventObservation:
    obs_id: str
    publication_id: str
    source_id: int
    author_id: str | None
    published_at: datetime
    url: str
    kind: str
    actor: str | None
    action: str | None
    object: str | None
    qualifiers: dict
    origin: str
    quote: str
    span: tuple[int, int]
    text_hash: str = ""
    context: str = ""

    def __post_init__(self) -> None:
        if not self.text_hash:
            self.text_hash = hashlib.sha256(fold(" ".join((self.quote or "").split())).encode()).hexdigest()[:16]


@dataclass
class EventGroup:
    event_id: str
    members: list[EventObservation] = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    headline: str = ""


def from_observation(obs: Observation) -> EventObservation:
    return EventObservation(
        obs_id=obs.obs_id,
        publication_id=obs.publication_id,
        source_id=obs.source_id,
        author_id=obs.author_id,
        published_at=obs.published_at,
        url=obs.url,
        kind=obs.kind,
        actor=obs.actor,
        action=obs.action,
        object=obs.object,
        qualifiers=dict(obs.qualifiers or {}),
        origin=obs.origin,
        quote=obs.quote,
        span=obs.span,
        context=getattr(obs, "context", ""),
    )


def _norm(value: object) -> str:
    return fold(str(value or "").strip())


def _url_key(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = (parts.netloc or "").casefold().removeprefix("www.")
    path = (parts.path or "").rstrip("/")
    if host in {"t.me", "telegram.me"}:
        return f"{host}{path}".casefold()
    if host:
        return f"{host}{path}".casefold()
    return url.casefold()


def event_key(obs: EventObservation) -> tuple[str, str, str]:
    return (_norm(obs.actor), _norm(obs.action), _norm(obs.object))


def _qual_items(obs: EventObservation) -> set[tuple[str, str]]:
    return {(_norm(k), _norm(v)) for k, v in (obs.qualifiers or {}).items() if _norm(v)}


def _canon(text: str, table: dict[str, tuple[str, ...]]) -> str:
    folded = _norm(text)
    if not folded:
        return ""
    for canon, aliases in table.items():
        if folded == canon or any(alias in folded for alias in aliases):
            return canon
    return folded


def _parse_number(raw: str) -> float | None:
    raw = raw.strip().replace("\u00a0", " ")
    if re.fullmatch(r"\d{1,3}(?:[ ,]\d{3})+(?:\.\d+)?", raw):
        raw = raw.replace(" ", "").replace(",", "")
    else:
        raw = raw.replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_amount_musd(text: str) -> float | None:
    """First money amount in the text, normalized to millions of USD ($224M == 224 млн == 224,000,000)."""
    for m in AMOUNT_RE.finditer(fold(text or "")):
        raw, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        value = _parse_number(raw)
        if value is None:
            continue
        if unit:
            return value * SCALE_MUSD.get(unit.rstrip("."), 1.0)
        return value / 1_000_000
    return None


def resolve_date(value: str, published_at: datetime | None) -> str | None:
    """ISO date for absolute or relative (вчера/today) dates; None when it cannot be resolved."""
    folded = fold(value or "")
    iso = ISO_DATE_RE.search(folded)
    if iso:
        return iso.group(1)
    if published_at is None:
        return None
    for word, delta in RELATIVE_DAYS.items():
        if re.search(rf"\b{word}\b", folded):
            return (published_at + timedelta(days=delta)).date().isoformat()
    m = DATE_RE.search(folded)
    if m:
        month = next((n for stem, n in MONTH_NUM.items() if m.group(2).startswith(stem)), None)
        if month:
            try:
                return published_at.replace(month=month, day=int(m.group(1))).date().isoformat()
            except ValueError:
                return None
    return None


def extract_key_quals(obs: EventObservation) -> dict[str, str]:
    """Key qualifiers: version, number/duration, ISO date, USD amount. Filled from fields and quote."""
    out: dict[str, str] = {}
    blob = " ".join(
        [
            obs.quote or "",
            _norm(obs.actor),
            _norm(obs.action),
            _norm(obs.object),
            " ".join(f"{k} {v}" for k, v in (obs.qualifiers or {}).items()),
        ]
    )
    folded = fold(blob)
    for key, val in _qual_items(obs):
        if key in {"version", "event_date", "date", "duration", "duration_s", "block_time", "change"}:
            dur = DURATION_RE.search(val)
            if dur:
                out["duration_s"] = dur.group(1)
            ver = VERSION_RE.search(val)
            if ver:
                out["version"] = fold(ver.group(1)).replace(" ", "")
            if key in {"event_date", "date"}:
                resolved = resolve_date(val, obs.published_at)
                if resolved:
                    out["event_date"] = resolved
            if key == "version" and "version" not in out:
                out["version"] = val
    dur = DURATION_RE.search(folded)
    if dur:
        out.setdefault("duration_s", dur.group(1))
    ver = VERSION_RE.search(folded)
    if ver:
        out.setdefault("version", fold(ver.group(1)).replace(" ", ""))
    if "event_date" not in out:
        resolved = resolve_date(obs.quote or "", obs.published_at)
        if resolved:
            out["event_date"] = resolved
    if "event_date" in out and obs.published_at is not None:
        # a date the quote does not state and that equals the publication day may be just the
        # publication day filled in by the classifier, not the day of the event
        stated = resolve_date(obs.quote or "", obs.published_at) is not None
        out["date_from_pub"] = str(not stated and out["event_date"] == obs.published_at.date().isoformat())
    amount = parse_amount_musd(obs.quote or "")
    if amount is None:
        amount = parse_amount_musd(str((obs.qualifiers or {}).get("amount") or ""))
    if amount is not None:
        out["amount"] = f"{amount:.4g}"
    return out


def _dates_compatible(qa: dict[str, str], qb: dict[str, str]) -> bool:
    """Equal ISO dates. Two explicit different dates are two events whatever the amounts.
    The only exception is a next-day report whose date is merely its publication day: it may
    match the explicit flow date one day earlier when one amount is the other rounded."""
    da, db = qa.get("event_date"), qb.get("event_date")
    if not da or not db or da == db:
        return True
    if (qa.get("date_from_pub") == "True") == (qb.get("date_from_pub") == "True"):
        return False
    stated, pub = (da, db) if qb.get("date_from_pub") == "True" else (db, da)
    try:
        gap = (datetime.fromisoformat(pub) - datetime.fromisoformat(stated)).days
    except ValueError:
        return False
    if gap == 1 and "amount" in qa and "amount" in qb:
        return _amounts_same_rounded(qa["amount"], qb["amount"])
    return False


def _amounts_same_rounded(a: str, b: str) -> bool:
    """The more precise amount rounds to the less precise one: 143.7 ~ 144, but 100 != 102."""
    try:
        xa, xb = float(a), float(b)
    except ValueError:
        return a == b
    decimals = min(len(a.partition(".")[2]), len(b.partition(".")[2]))
    return round(xa, decimals) == round(xb, decimals)


def _flow_days_compatible(a: EventObservation, b: EventObservation, qa: dict, qb: dict) -> bool:
    """Daily fund flows: without a stated date the report day is the publication day (±1 for time zones)."""
    da = qa.get("event_date") or a.published_at.date().isoformat()
    db = qb.get("event_date") or b.published_at.date().isoformat()
    try:
        return abs((datetime.fromisoformat(da) - datetime.fromisoformat(db)).days) <= 1
    except ValueError:
        return da == db


def _key_quals_compatible(qa: dict[str, str], qb: dict[str, str]) -> bool:
    for key in ("duration_s", "version"):
        if key in qa and key in qb and qa[key] != qb[key]:
            return False
    return _dates_compatible(qa, qb)


def _object_canon(obs: EventObservation) -> str:
    """Canonical object; ETF is qualified by its asset so BTC-ETF and ETH-ETF never share a key."""
    head = f"{_norm(obs.object)} {_norm(obs.action)}"
    for text in (head, fold(obs.quote or "")):
        for m in re.finditer(r"(?<![a-z])([a-z]{2,5})(?:[-\s]?etf)", text):
            if m.group(1) in TICKERS:
                return f"{m.group(1)}_etf"
    obj = _canon(obs.object or "", OBJECT_ALIASES)
    if "etf" in fold(obs.context or "") or "etf" in head:
        # a row of an ETF flow table ("#ETH = +$270M" under "ETF flows"): the row ticker names the fund
        tickers = [t for t in re.findall(r"#?([a-z]{2,5})\b", fold(obs.quote or "")) if t in TICKERS]
        if obj in TICKERS:
            return f"{obj}_etf"
        if tickers:
            return f"{tickers[0]}_etf"
        return "etf"
    return obj


def subject_key(obs: EventObservation) -> tuple[str, str, str, tuple[tuple[str, str], ...]]:
    actor = _canon(obs.actor or "", ACTOR_ALIASES)
    action = _canon(obs.action or "", ACTION_ALIASES)
    obj = _object_canon(obs)
    if obj.endswith("etf") and action not in {"inflow", "outflow"}:
        quote = fold(obs.quote or "")
        if re.search(r"\+\s*\$\s*\d", quote):
            action = "inflow"
        elif re.search(r"[-−]\s*\$\s*\d", quote):
            action = "outflow"
        else:
            action = _canon(quote, {k: ACTION_ALIASES[k] for k in ("inflow", "outflow")}) or action
    quals = extract_key_quals(obs)
    key_quals = tuple(sorted((k, quals[k]) for k in ("duration_s", "version", "event_date") if k in quals))
    return (actor, action, obj, key_quals)


def ticker_only(a: EventObservation, b: EventObservation) -> bool:
    """Same ticker/object, but actor/action/qualifiers do not match — do not merge."""
    obj_a, obj_b = _norm(a.object), _norm(b.object)
    if not obj_a or obj_a != obj_b:
        sa, sb = subject_key(a), subject_key(b)
        tickers = {"zec", "eth", "btc", "sol"}
        if sa[2] in tickers and sa[2] == sb[2] and sa[1] != sb[1]:
            return True
        return False
    if event_key(a) == event_key(b) and event_key(a)[0] and event_key(a)[1]:
        return False
    sa, sb = subject_key(a), subject_key(b)
    if sa[1] and sa[1] == sb[1] and sa[2] and sa[2] == sb[2]:
        return False
    return event_key(a) != event_key(b)


def _amounts_compatible(a: str, b: str) -> bool:
    try:
        xa, xb = float(a), float(b)
    except ValueError:
        return a == b
    if xa <= 0 or xb <= 0:
        return xa == xb
    return min(xa, xb) / max(xa, xb) >= 0.95


def conflicting(a: EventObservation, b: EventObservation) -> bool:
    qa, qb = extract_key_quals(a), extract_key_quals(b)
    if not _key_quals_compatible(qa, qb):
        return True
    sa, sb = subject_key(a), subject_key(b)
    if sa[2].endswith("_etf") and sb[2].endswith("_etf"):
        if sa[2] != sb[2] or not _flow_days_compatible(a, b, qa, qb):
            return True
    if "amount" in qa and "amount" in qb and not _amounts_compatible(qa["amount"], qb["amount"]):
        return True
    raw_a, raw_b = dict(_qual_items(a)), dict(_qual_items(b))
    for key in set(raw_a) & set(raw_b):
        if raw_a[key] != raw_b[key] and key not in {"duration", "block_time", "change"}:
            if key in {"stage"} and raw_a[key] != raw_b[key]:
                return True
            if key in {"asset"} and raw_a[key] != raw_b[key]:
                return True
    if _norm(a.object) and _norm(b.object) and _norm(a.object) != _norm(b.object):
        if _norm(a.action) == _norm(b.action) and _norm(a.action):
            sa, sb = subject_key(a), subject_key(b)
            if sa[2] and sa[2] == sb[2]:
                return False
            return True
    sa, sb = subject_key(a), subject_key(b)
    if sa[1] and sb[1] and sa[1] != sb[1] and {sa[1], sb[1]} == {"vote", "upgrade"}:
        return True
    return False


def _actors_differ(sa: tuple, sb: tuple) -> bool:
    """Two named actors with no shared word: Binance vs Coinbase listing, but also hackers vs
    attackers or Мосбиржа vs Moscow Exchange. The strings cannot tell a second actor from a
    synonym, so this is not a conflict; it only stops a merge without the judge.
    Fund flows are exempt: their actor is whoever reported the table, not who acted."""
    if sa[2].endswith("etf") or sb[2].endswith("etf"):
        return False
    if not sa[0] or not sb[0] or sa[0] == sb[0]:
        return False
    return not set(re.findall(r"\w+", sa[0])) & set(re.findall(r"\w+", sb[0]))


def same_event_deterministic(a: EventObservation, b: EventObservation) -> bool:
    # identical wording is not identity: "Today ... $100M" on two days is two flows
    if conflicting(a, b):
        return False
    # a bare "ZEC" quote hashes the same for "гигачад сделал ставки" and "я не шарю"
    if _actors_differ(subject_key(a), subject_key(b)):
        return False
    return _same_apart_from_actors(a, b)


def _same_apart_from_actors(a: EventObservation, b: EventObservation) -> bool:
    sa, sb = subject_key(a), subject_key(b)
    if a.text_hash and a.text_hash == b.text_hash:
        return True
    if ticker_only(a, b):
        return False
    qa, qb = extract_key_quals(a), extract_key_quals(b)
    if sa[1] and sa[1] == sb[1] and sa[2] and sa[2] == sb[2]:
        shared = set(qa) & set(qb) & {"duration_s", "version", "event_date"}
        if shared and _key_quals_compatible(qa, qb):
            return True
        if "amount" in qa and "amount" in qb and _amounts_compatible(qa["amount"], qb["amount"]):
            return True
        if sa[3] and sa[3] == sb[3]:
            return True
        if not sa[3] and not sb[3]:
            return True
    if (
        sa[2] == sb[2] == "block_time"
        and qa.get("duration_s")
        and qa.get("duration_s") == qb.get("duration_s")
        and {sa[1], sb[1]} <= {"vote", "reduce", ""}
    ):
        return True
    key_a, key_b = event_key(a), event_key(b)
    if key_a == key_b and all(key_a):
        qa, qb = _qual_items(a), _qual_items(b)
        return not qa or not qb or bool(qa & qb) or qa == qb
    ua, ub = _url_key(a.url), _url_key(b.url)
    if ua and ua == ub and _norm(a.object) == _norm(b.object) and _norm(a.action) == _norm(b.action):
        return bool(_norm(a.object) and _norm(a.action))
    return False


def _shared_specific_entity(a: EventObservation, b: EventObservation) -> bool:
    """Specific entity: shared key qualifier or the same non-ticker object. Action-only is not enough."""
    qa, qb = extract_key_quals(a), extract_key_quals(b)
    for key in ("duration_s", "version", "event_date"):
        if key in qa and key in qb and qa[key] == qb[key]:
            return True
    sa, sb = subject_key(a), subject_key(b)
    if sa[2] and sa[2] == sb[2] and sa[2] not in {"zec", "eth", "btc", "sol"}:
        return True
    if "amount" in qa and "amount" in qb and _amounts_compatible(qa["amount"], qb["amount"]):
        return True
    return False


def candidate_pair(a: EventObservation, b: EventObservation, horizon: timedelta = timedelta(hours=72)) -> bool:
    """Strong judge filter: shared specific entity plus action/object/qualifier overlap, ±72h."""
    if ticker_only(a, b) or conflicting(a, b):
        return False
    # BitMine vs $BMNR: everything matches but the actor, and only the judge knows the alias
    if _actors_differ(subject_key(a), subject_key(b)) and _same_apart_from_actors(a, b):
        return True
    if a.text_hash == b.text_hash:
        return True
    ua, ub = _url_key(a.url), _url_key(b.url)
    if ua and ua == ub:
        return True
    if abs(a.published_at - b.published_at) > horizon:
        return False
    if not _shared_specific_entity(a, b):
        return False
    sa, sb = subject_key(a), subject_key(b)
    qa, qb = extract_key_quals(a), extract_key_quals(b)
    action_match = bool(sa[1] and sa[1] == sb[1])
    object_match = bool(sa[2] and sa[2] == sb[2])
    qual_match = bool(set(qa.items()) & set(qb.items()))
    return action_match or object_match or qual_match


def _unique_publications(members: list[EventObservation]) -> list[EventObservation]:
    by_pub: dict[str, EventObservation] = {}
    for m in members:
        if m.publication_id not in by_pub:
            by_pub[m.publication_id] = m
    return list(by_pub.values())


HEADLINE_LIMIT = 180


def clip_headline(quote: str) -> str:
    """First line of the quote; a long line is cut at a word boundary so no number is split."""
    line = quote.strip().split("\n")[0]
    if len(line) <= HEADLINE_LIMIT:
        return line
    cut = line[:HEADLINE_LIMIT]
    if not line[HEADLINE_LIMIT].isspace() and " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:—-") + "…"


def group_counts(members: list[EventObservation]) -> dict[str, int]:
    uniq = _unique_publications(members)
    known = {m.author_id for m in uniq if m.author_id}
    return {
        "events": 1,
        "publications": len(uniq),
        "channels": len({m.source_id for m in uniq}),
        "known_authors": len(known),
        "unknown_authors": sum(1 for m in uniq if not m.author_id),
        "found_origins": sum(1 for m in uniq if m.origin == "own"),
        "reprints": sum(1 for m in uniq if m.origin in {"retelling", "repost"}),
        "unknown_origin": sum(1 for m in uniq if m.origin == "unknown"),
    }


SMALL_GROUP = 4
JudgeFn = Callable[[EventObservation, EventObservation], str]
JudgeManyFn = Callable[[list[tuple[EventObservation, EventObservation]]], list[str]]


def _pair_key(a: EventObservation, b: EventObservation) -> tuple[str, str]:
    return tuple(sorted((a.obs_id, b.obs_id)))


def _deterministic_join(obs: EventObservation, group: list[EventObservation]) -> bool:
    return all(same_event_deterministic(obs, m) for m in group)


def _judge_targets(
    left: list[EventObservation], right: list[EventObservation]
) -> list[tuple[EventObservation, EventObservation]]:
    members_l = left if len(left) <= SMALL_GROUP else [left[0], left[-1]]
    members_r = right if len(right) <= SMALL_GROUP else [right[0], right[-1]]
    return [(a, b) for a in members_l for b in members_r]


def _groups_conflict(left: list[EventObservation], right: list[EventObservation]) -> bool:
    return any(ticker_only(a, b) or conflicting(a, b) for a in left for b in right)


def _judge_join(
    left: list[EventObservation],
    right: list[EventObservation],
    cache: dict[tuple[str, str], str],
) -> bool:
    if _groups_conflict(left, right):
        return False
    if not candidate_pair(left[0], right[0]):
        return False
    for a, b in _judge_targets(left, right):
        if same_event_deterministic(a, b):
            continue
        if cache.get(_pair_key(a, b)) != "same":
            return False
    return True


def group_events(
    observations: list[EventObservation],
    judge: JudgeFn | None = None,
    judge_many: JudgeManyFn | None = None,
) -> list[EventGroup]:
    """Deterministic blocks first; judge only strong-filter pairs vs a representative.

    A member joins a group only if compatible with every member (deterministic
    conflicting/ticker_only). Judge is called against all members of small
    groups (≤4) and against the representative plus last member otherwise.
    No ticker-only merge and no transitive clique expansion.
    """
    events = [o for o in observations if o.kind == "event"]
    events.sort(key=lambda o: (o.published_at, o.obs_id))
    groups: list[list[EventObservation]] = []
    for obs in events:
        placed = False
        for g in groups:
            if _deterministic_join(obs, g):
                g.append(obs)
                placed = True
                break
        if not placed:
            groups.append([obs])

    many = judge_many
    if many is None and judge is not None:
        def many(pairs: list[tuple[EventObservation, EventObservation]]) -> list[str]:
            return [judge(a, b) for a, b in pairs]

    if many is not None:
        cache: dict[tuple[str, str], str] = {}
        needed: list[tuple[EventObservation, EventObservation]] = []
        seen: set[tuple[str, str]] = set()
        for i, later in enumerate(groups):
            for earlier in groups[:i]:
                if _groups_conflict(later, earlier) or not candidate_pair(later[0], earlier[0]):
                    continue
                for a, b in _judge_targets(later, earlier):
                    key = _pair_key(a, b)
                    if key in seen or same_event_deterministic(a, b):
                        continue
                    seen.add(key)
                    needed.append((a, b))
        if needed:
            for (a, b), decision in zip(needed, many(needed)):
                cache[_pair_key(a, b)] = decision
        merged: list[list[EventObservation]] = []
        for g in groups:
            placed = False
            for h in merged:
                if _judge_join(g, h, cache):
                    h.extend(g)
                    placed = True
                    break
            if not placed:
                merged.append(g)
        groups = merged

    out: list[EventGroup] = []
    for i, members in enumerate(groups, start=1):
        members = sorted(members, key=lambda m: m.published_at)
        headline = clip_headline(members[0].quote)
        gid = f"e{i}-{members[0].text_hash}"
        out.append(EventGroup(event_id=gid, members=members, counts=group_counts(members), headline=headline))
    return out


def group_to_dict(group: EventGroup) -> dict[str, Any]:
    return {
        "event_id": group.event_id,
        "headline": group.headline,
        "counts": group.counts,
        "actor": group.members[0].actor,
        "action": group.members[0].action,
        "object": group.members[0].object,
        "qualifiers": group.members[0].qualifiers,
        "members": [
            {
                "obs_id": m.obs_id,
                "publication_id": m.publication_id,
                "source_id": m.source_id,
                "author_id": m.author_id,
                "published_at": m.published_at.isoformat(),
                "url": m.url,
                "quote": m.quote,
                "span": list(m.span),
                "origin": m.origin,
            }
            for m in group.members
        ],
    }
