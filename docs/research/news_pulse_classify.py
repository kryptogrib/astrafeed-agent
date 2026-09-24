"""Rule segmentation plus optional LLM labels for topic-candidate segments."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from news_pulse_load import Publication, TopicAliases, fold

KINDS = ("event", "author_position", "redistribution", "participant_reaction", "promo_service")
ORIGINS = ("own", "retelling", "repost", "unknown")
SOURCE_ROLES = ("official", "editorial", "author", "participant", "unknown")
VERIFICATIONS = ("unverified", "source_statement", "corroborated", "disputed")

TICKERS = frozenset(
    "btc eth sol zec xrp bnb doge ton sui hype gram arb uni ada trx near op apt".split()
)
PROMO_RE = re.compile(
    r"(?i)\b(подписывайтесь|подпишись|реклама|промокод|реферальн|giveaway|airdrop claim|наш канал)\b|t\.me/\+"
)
PRICE_HINT = re.compile(r"\$\s*\d|\d[\d\s.,]{0,10}\s*\$|[><=≈~]\s*\$?\d")
TICKER_TOKEN = re.compile(r"(?i)(?<![0-9A-Za-zА-Яа-яЁё])[#$]?([A-Za-z]{2,6}|зкеш\w*)(?![0-9A-Za-zА-Яа-яЁё])")
SIGNATURE_RE = re.compile(r"(?i)^(?:@\w+|crypto headlines|via\s+\S+|@decenter)$")
HASHTAG_ONLY = re.compile(r"^(?:[#@]\w+[\s,]*)+$")
EVENT_STEM = re.compile(
    r"(?i)проголосова|одобр|запуск|листинг|обновл|upgrade|announce|вывел|переезж|"
    r"targets|предложил|сокращен|ускор|approved|voted|launch|listing|"
    r"приток|отток|минт|whitelist|\bwl\b"
)
DIGEST_ITEM = re.compile(
    r"^(?:[•●▪◦‣\-–—]\s|[▫◾◽]|\d+[.)]\s|[🔴👍🔘📉📈🔍📆🍒👋🔓🇷🇺🇺🇸💰🔹🪙💥✴️⬆️]|[\U0001F300-\U0001FAFF])"
)
FLOW_HEADER = re.compile(r"(?i)\betf\b.*(?:поток|приток|отток|flow)|(?:поток|приток|отток|flow).*\betf\b")
SIGNED_AMOUNT = re.compile(r"[+\-−]\s*\$\s*\d")
LINK_ONLY = re.compile(r"^(?:https?://\S+|t\.me/\S+)(?:\s*)$", re.I)


@dataclass
class Mention:
    surface: str
    status: str
    start: int
    end: int


@dataclass
class Segment:
    seg_id: str
    publication_id: str
    text: str
    span: tuple[int, int]
    role: str
    mentions: list[Mention] = field(default_factory=list)
    is_candidate: bool = False
    context: str = ""


@dataclass
class Observation:
    obs_id: str
    publication_id: str
    source_id: int
    author_id: str | None
    published_at: Any
    url: str
    span: tuple[int, int]
    quote: str
    kind: str
    actor: str | None
    action: str | None
    object: str | None
    qualifiers: dict
    origin: str
    source_role: str
    verification_status: str
    topic_mentions: list[dict]
    status: str = "ok"
    held_reason: str | None = None
    segment_role: str = "body"
    text: str = ""
    context: str = ""
    topic_role: str = "subject"


def find_mentions(text: str, topic: TopicAliases) -> list[Mention]:
    found: list[Mention] = []
    raw = text or ""
    folded = fold(raw)
    surfaces = sorted(topic.confirmed, key=len, reverse=True)
    for surface in surfaces:
        if not surface:
            continue
        pattern = re.compile(rf"(?<![0-9A-Za-zА-Яа-яЁё_]){re.escape(surface)}(?![0-9A-Za-zА-Яа-яЁё_])", re.I)
        for m in pattern.finditer(folded):
            found.append(Mention(surface=raw[m.start() : m.end()], status="confirmed", start=m.start(), end=m.end()))
        cash = re.compile(rf"(?<![0-9A-Za-z])[$#]{re.escape(surface)}(?![0-9A-Za-z])", re.I)
        for m in cash.finditer(folded):
            found.append(Mention(surface=raw[m.start() : m.end()], status="confirmed", start=m.start(), end=m.end()))
    for row in topic.ambiguous:
        pattern = re.compile(rf"(?<![0-9A-Za-zА-Яа-яЁё_]){re.escape(row.surface)}(?![0-9A-Za-zА-Яа-яЁё_])", re.I)
        for m in pattern.finditer(folded):
            window = folded[max(0, m.start() - 60) : m.end() + 60]
            if row.reject and row.reject.search(window):
                continue
            status = "ambiguous"
            if row.support and not row.support.search(window):
                continue
            if row.support and row.support.search(window):
                status = "ambiguous"
            found.append(Mention(surface=raw[m.start() : m.end()], status=status, start=m.start(), end=m.end()))
    uniq: dict[tuple[int, int, str], Mention] = {}
    for m in found:
        uniq[(m.start, m.end, m.status)] = m
    return sorted(uniq.values(), key=lambda x: (x.start, x.end))


def line_role(line: str) -> str:
    s = line.strip()
    if not s:
        return "blank"
    if SIGNATURE_RE.fullmatch(s):
        return "footer"
    if HASHTAG_ONLY.fullmatch(s):
        return "footer"
    if PROMO_RE.search(s) and len(s) < 120:
        return "promo"
    words = re.findall(r"[A-Za-zА-Яа-яЁё]{3,}", s)
    tickers = [t.casefold() for t in TICKER_TOKEN.findall(s)]
    ticker_hits = [t for t in tickers if t in TICKERS or t.startswith("зкеш")]
    has_price = bool(PRICE_HINT.search(s))
    prose = [w for w in words if w.casefold() not in TICKERS and not w.startswith("#")]
    if LINK_ONLY.fullmatch(s):
        return "link"
    if ticker_hits and has_price and EVENT_STEM.search(s):
        return "body"
    if ticker_hits and has_price and len(prose) <= 2:
        return "quote_line"
    if ticker_hits and has_price and len(s) < 80 and len(prose) <= 4:
        return "quote_line"
    return "body"


def _line_spans(text: str) -> list[tuple[int, int, str]]:
    out = []
    start = 0
    for chunk in (text or "").splitlines(keepends=True):
        out.append((start, start + len(chunk), chunk))
        start += len(chunk)
    if not out:
        out.append((0, 0, ""))
    return out


def segment_publication(pub: Publication, topic: TopicAliases) -> list[Segment]:
    text = pub.text or ""
    lines = _line_spans(text)
    roles = [line_role(chunk) for _, _, chunk in lines]
    flow_header = next(
        (chunk.strip() for role, (_, _, chunk) in zip(roles, lines) if role == "body" and FLOW_HEADER.search(chunk)),
        "",
    )
    flow_rows: set[int] = set()
    if flow_header:
        # ETF flow tables: "#ETH = +$269,980,000" is a per-asset event line, not a price quote.
        for i, (_, _, chunk) in enumerate(lines):
            if roles[i] == "quote_line" and SIGNED_AMOUNT.search(chunk):
                roles[i] = "body"
                flow_rows.add(i)
    last_body = -1
    for i, role in enumerate(roles):
        if role == "body" and lines[i][2].strip():
            last_body = i
    for i in range(last_body + 1, len(roles)):
        if roles[i] in {"quote_line", "footer", "promo", "blank"}:
            if roles[i] == "quote_line":
                roles[i] = "footer"
    segments: list[Segment] = []
    i = 0
    n = 0
    while i < len(lines):
        role = roles[i]
        if role == "blank":
            i += 1
            continue
        j = i + 1
        digest = bool(DIGEST_ITEM.match(lines[i][2].lstrip())) if role == "body" else False
        if role == "body" and digest:
            j = i + 1
        elif role == "body":
            while j < len(lines) and roles[j] in {"body", "blank"}:
                if roles[j] == "body" and DIGEST_ITEM.match(lines[j][2].lstrip()):
                    break
                if roles[j] == "body" and lines[j][2].strip() and lines[i][2].endswith("\n\n"):
                    break
                if roles[j] == "body" and i < j and lines[j - 1][2].endswith("\n") and lines[j][2].strip():
                    prev_blank = roles[j - 1] == "blank"
                    if prev_blank:
                        break
                j += 1
        else:
            while j < len(lines) and roles[j] == role:
                j += 1
        start, end = lines[i][0], lines[j - 1][1]
        chunk = text[start:end]
        mentions = find_mentions(chunk, topic)
        is_candidate = bool(mentions) and role == "body" and not PROMO_RE.search(chunk) and role != "link"
        seg = Segment(
            seg_id=f"{pub.pub_id}#s{n}",
            publication_id=pub.pub_id,
            text=chunk,
            span=(start, end),
            role=role,
            mentions=mentions,
            is_candidate=is_candidate,
            context=flow_header if i in flow_rows else "",
        )
        segments.append(seg)
        n += 1
        i = j
    bodies = [s for s in segments if s.role == "body" and s.text.strip()]
    if not bodies:
        for s in segments:
            if s.mentions and s.role in {"quote_line", "footer"} and PRICE_HINT.search(s.text):
                s.is_candidate = True
    return segments


def _quote_span(text: str, quote: str | None, span: Any) -> tuple[tuple[int, int], str] | None:
    if not quote:
        return None
    if isinstance(span, (list, tuple)) and len(span) == 2:
        try:
            a, b = int(span[0]), int(span[1])
        except (TypeError, ValueError):
            a = b = -1
        if 0 <= a <= b <= len(text) and text[a:b] == quote:
            return (a, b), quote
    idx = text.find(quote)
    if idx >= 0:
        return (idx, idx + len(quote)), quote
    collapsed = " ".join(quote.split())
    hay = " ".join(text.split())
    if collapsed and collapsed in hay:
        # cannot recover exact offsets after whitespace fold
        idx = text.find(quote.strip())
        if idx >= 0:
            q = quote.strip()
            return (idx, idx + len(q)), q
    return None


def observation_from_label(seg: Segment, pub: Publication, label: dict, *, fallback: str = "held") -> Observation:
    kind = label.get("kind") if label.get("kind") in KINDS else None
    origin = label.get("origin") if label.get("origin") in ORIGINS else "unknown"
    role = label.get("source_role") if label.get("source_role") in SOURCE_ROLES else "unknown"
    ver = label.get("verification_status") if label.get("verification_status") in VERIFICATIONS else "unverified"
    quote = label.get("quote")
    located = _quote_span(seg.text, quote, label.get("span"))
    abs_span = seg.span
    quote_text = (quote or "").strip()
    status = "ok"
    reason = None
    if pub.kind == "comment" and kind in {"event", "redistribution", "promo_service"}:
        kind = "participant_reaction"
        role = "participant"
    if kind is None:
        status, kind, reason = fallback, "held" if fallback == "held" else "unclear", "invalid_or_missing_kind"
    if quote and located is None:
        status, reason = fallback, "quote_not_in_text"
        kind = "held" if fallback == "held" else kind or "unclear"
    elif located:
        local, quote_text = located
        abs_span = (seg.span[0] + local[0], seg.span[0] + local[1])
        if pub.text[abs_span[0] : abs_span[1]] != quote_text:
            status, reason = fallback, "span_mismatch"
    elif not quote and kind in {"event", "author_position"}:
        status, reason = fallback, "missing_quote"
    quals = label.get("qualifiers") if isinstance(label.get("qualifiers"), dict) else {}
    return Observation(
        obs_id=seg.seg_id,
        publication_id=pub.pub_id,
        source_id=pub.source_id,
        author_id=pub.author_id,
        published_at=pub.published_at,
        url=pub.url,
        span=abs_span,
        quote=quote_text or seg.text[:180],
        kind=kind or "unclear",
        actor=label.get("actor") or None,
        action=label.get("action") or None,
        object=label.get("object") or None,
        qualifiers=quals,
        origin=origin,
        source_role=role if pub.kind != "comment" else "participant",
        verification_status=ver,
        topic_mentions=[{"text": m.surface, "status": m.status} for m in seg.mentions],
        status=status,
        held_reason=reason,
        segment_role=seg.role,
        text=seg.text,
        context=seg.context,
        topic_role="context" if label.get("topic_role") == "context" else "subject",
    )


def rule_label(seg: Segment, pub: Publication) -> dict:
    if seg.role == "link" or (seg.role in {"quote_line", "footer"} and not seg.is_candidate) or seg.role == "promo":
        return {
            "kind": "promo_service",
            "origin": "unknown",
            "source_role": "unknown",
            "verification_status": "unverified",
            "quote": seg.text.strip()[:160],
            "span": [0, min(len(seg.text), len(seg.text.strip()[:160]) if False else len(seg.text))],
            "actor": None,
            "action": None,
            "object": None,
            "qualifiers": {},
        }
    if pub.kind == "comment":
        kind = "participant_reaction"
    elif EVENT_STEM.search(seg.text) or (seg.is_candidate and PRICE_HINT.search(seg.text) and len(seg.text) < 80):
        kind = "event"
    elif re.search(r"(?i)\b(думаю|имхо|по-моему|кажется|прогноз)\b", seg.text):
        kind = "author_position"
    else:
        kind = "author_position" if pub.kind == "post" else "participant_reaction"
    quote = seg.text.strip()[:180]
    idx = seg.text.find(quote) if quote else 0
    return {
        "kind": kind,
        "origin": "unknown",
        "source_role": "participant" if pub.kind == "comment" else "unknown",
        "verification_status": "unverified",
        "quote": quote,
        "span": [idx, idx + len(quote)],
        "actor": None,
        "action": None,
        "object": None,
        "qualifiers": {},
    }


def classify_segments(
    publications: list[Publication],
    topic: TopicAliases,
    llm: Callable[[list[dict]], list[dict]] | None = None,
) -> list[Observation]:
    """Rules first; LLM only for body candidates. Duplicate texts share one LLM label."""
    segs_by_pub: list[tuple[Publication, list[Segment]]] = []
    candidates: list[tuple[Publication, Segment]] = []
    for pub in publications:
        segs = segment_publication(pub, topic)
        segs_by_pub.append((pub, segs))
        for seg in segs:
            if seg.is_candidate:
                candidates.append((pub, seg))
    labels: dict[str, dict] = {}
    pending: list[tuple[str, dict]] = []
    seen_hash: dict[str, str] = {}
    for pub, seg in candidates:
        key = " ".join(fold(seg.text).split())
        if key in seen_hash:
            labels[seg.seg_id] = labels.get(seen_hash[key], {})
            continue
        seen_hash[key] = seg.seg_id
        item = {
            "id": seg.seg_id,
            "text": seg.text[:1200],
            "mentions": [{"text": m.surface, "status": m.status} for m in seg.mentions],
            "kind_hint": pub.kind,
            "url": pub.url,
            "time": pub.published_at.isoformat() if hasattr(pub.published_at, "isoformat") else str(pub.published_at),
        }
        if seg.context:
            item["context"] = seg.context[:200]
        pending.append((seg.seg_id, item))
    llm_out: dict[str, dict] = {}
    if llm and pending:
        raw = llm([item for _, item in pending])
        for row in raw:
            if isinstance(row, dict) and row.get("id"):
                llm_out[str(row["id"])] = row
    observations: list[Observation] = []
    cand_ids = {seg.seg_id for _, seg in candidates}
    for pub, segs in segs_by_pub:
        for seg in segs:
            if seg.seg_id in cand_ids:
                label = llm_out.get(seg.seg_id) or labels.get(seg.seg_id)
                if not label:
                    key = " ".join(fold(seg.text).split())
                    donor = seen_hash.get(key)
                    label = llm_out.get(donor or "", None)
                if label:
                    observations.append(observation_from_label(seg, pub, label))
                elif llm is not None and seg.seg_id in {s for s, _ in pending} and seg.seg_id not in llm_out:
                    observations.append(observation_from_label(seg, pub, rule_label(seg, pub) | {"kind": "held"}, fallback="held"))
                    observations[-1].status = "not_processed"
                    observations[-1].held_reason = "not_processed"
                    observations[-1].kind = "held"
                else:
                    observations.append(observation_from_label(seg, pub, rule_label(seg, pub)))
            elif seg.mentions and seg.role in {"quote_line", "footer", "promo", "link"}:
                observations.append(observation_from_label(seg, pub, rule_label(seg, pub)))
    return observations
