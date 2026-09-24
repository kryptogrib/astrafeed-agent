"""Read-only snapshot of publications and comments for news-first Pulse.

Window is UTC [start, end). Date-only 'YYYY-MM-DD..YYYY-MM-DD' is inclusive by
calendar days: start at 00:00 UTC of the first day, end at 00:00 UTC of the day
after the last. Everything at or after cutoff is dropped BEFORE any processing.
Database is opened only as sqlite3 URI mode=ro. Stdlib only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

WINDOW_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$")
DT_WINDOW_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\.\."
    r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))$"
)
WORD_BOUND = r"[0-9A-Za-zА-Яа-яЁё_]"
WINDOW_ERROR = "window must be YYYY-MM-DD..YYYY-MM-DD or ISO_DATETIME..ISO_DATETIME"


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime
    requested: str


@dataclass(frozen=True)
class Source:
    source_id: int
    platform: str
    external_id: str
    handle: str | None
    role: str = "unknown"
    role_basis: str = "no registry in snapshot"


@dataclass(frozen=True)
class Actor:
    actor_id: str | None
    kind: str = "unknown"


@dataclass(frozen=True)
class Publication:
    pub_id: str
    platform: str
    source_id: int
    message_external_id: str
    author_id: str | None
    published_at: datetime
    discovered_at: datetime | None
    url: str
    text: str
    parent_id: str | None
    thread_id: str | None
    kind: str
    has_media: bool
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AmbiguousAlias:
    surface: str
    reject: re.Pattern[str] | None
    support: re.Pattern[str] | None


@dataclass(frozen=True)
class TopicAliases:
    topic: str
    confirmed: frozenset[str]
    ambiguous: tuple[AmbiguousAlias, ...] = ()


@dataclass(frozen=True)
class Snapshot:
    window: Window
    cutoff: datetime
    db_md5: str
    sources: dict[int, Source]
    publications: list[Publication]
    comments: list[Publication]
    dropped_after_cutoff: int


BUILTIN_TOPICS: dict[str, tuple[str, ...]] = {
    "zec": ("zec", "zcash"),
    "eth": ("eth", "ethereum", "ether"),
}


def open_ro(db_path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")
    return db


def db_md5(db_path: str | Path) -> str:
    return hashlib.md5(Path(db_path).read_bytes()).hexdigest()


def parse_ts(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(" ", "T", 1)
    text = re.sub(r"\.\d+", "", text)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if not re.search(r"[+-]\d{2}:\d{2}$", text):
        text += "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_window(window: str) -> Window:
    text = (window or "").strip()
    m = WINDOW_RE.fullmatch(text)
    if m:
        try:
            lo = datetime.fromisoformat(m.group(1)).replace(tzinfo=UTC)
            hi = datetime.fromisoformat(m.group(2)).replace(tzinfo=UTC)
        except ValueError as e:
            raise ValueError(f"window {window!r}: {e}") from e
        if lo > hi:
            raise ValueError(f"window {window!r}: start is after end")
        return Window(start=lo, end=hi + timedelta(days=1), requested=f"{m.group(1)}..{m.group(2)}")
    m = DT_WINDOW_RE.fullmatch(text)
    if not m:
        raise ValueError(WINDOW_ERROR)
    lo, hi = parse_ts(m.group(1)), parse_ts(m.group(2))
    if lo is None or hi is None:
        raise ValueError(WINDOW_ERROR)
    if lo > hi:
        raise ValueError(f"window {window!r}: start is after end")
    return Window(start=lo, end=hi, requested=text)


def previous_window(window: Window) -> Window:
    delta = window.end - window.start
    end = window.start
    start = end - delta
    if "T" in window.requested:
        requested = f"{start.isoformat()}..{end.isoformat()}"
    else:
        last_day = (end - timedelta(days=1)).date().isoformat()
        requested = f"{start.date().isoformat()}..{last_day}"
    return Window(start=start, end=end, requested=requested)


def window_dir_name(window: str) -> str:
    return window.replace(":", "-").replace("+", "-")


def parse_aliases_env(text: str | None) -> dict[str, list[str]]:
    """ALIASES=arc:arc,circle;aave:aave or ALIASES=name1,name2 (applied to current topic)."""
    raw = (text or "").strip()
    if not raw:
        return {}
    if ":" in raw:
        out: dict[str, list[str]] = {}
        for part in raw.split(";"):
            chunk = part.strip()
            if not chunk:
                continue
            if ":" in chunk:
                topic, names = chunk.split(":", 1)
                out[topic.strip()] = [n.strip() for n in names.split(",") if n.strip()]
            else:
                out.setdefault(chunk, [chunk])
        return out
    return {"": [n.strip() for n in raw.split(",") if n.strip()]}


def fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").casefold()


def _cluster_topics(rows: list[dict]) -> dict[str, set[str]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for key, names in BUILTIN_TOPICS.items():
        for n in names:
            union(key, n)
    for r in rows:
        cand = (r.get("candidate") or "").strip()
        if not cand or cand == "-":
            continue
        union(cand, cand)
        if r.get("relation") == "asset_symbol":
            union(cand, r["surface"].strip())
    clusters: dict[str, set[str]] = {}
    for name in list(parent):
        clusters.setdefault(find(name), set()).add(name)
    out: dict[str, set[str]] = {}
    for members in clusters.values():
        keys = set(members)
        for seed, names in BUILTIN_TOPICS.items():
            if seed in members or members & set(names):
                keys.add(seed)
                keys.update(names)
        for k in keys:
            out.setdefault(k, set()).update(keys)
    return out


def load_aliases(path: str | Path | None = None, extra: dict[str, list[str]] | None = None) -> dict[str, TopicAliases]:
    rows: list[dict] = []
    if path and Path(path).exists():
        lines = [ln for ln in Path(path).read_text().splitlines() if ln.strip() and not ln.startswith("#")]
        rows = list(csv.DictReader(lines, delimiter="\t"))
    clusters = _cluster_topics(rows)
    confirmed: dict[str, set[str]] = {k: {fold(k), *(fold(x) for x in v)} for k, v in BUILTIN_TOPICS.items()}
    ambiguous: dict[str, list[AmbiguousAlias]] = {k: [] for k in BUILTIN_TOPICS}
    for r in rows:
        cand = (r.get("candidate") or "").strip()
        surface = fold(r.get("surface") or "")
        if not cand or cand == "-" or not surface:
            continue
        topics = clusters.get(cand, {cand})
        cond = dict(part.strip().split("=", 1) for part in (r.get("condition") or "").split("; ") if "=" in part)
        if r.get("status") == "ambiguous":
            item = AmbiguousAlias(
                surface=surface,
                reject=re.compile(cond["reject"], re.I) if "reject" in cond else None,
                support=re.compile(cond["support"], re.I) if "support" in cond else None,
            )
            for topic in topics:
                ambiguous.setdefault(topic, []).append(item)
        elif r.get("status") == "confirmed":
            for topic in topics:
                confirmed.setdefault(topic, set()).update({surface, fold(cand), *{fold(x) for x in topics}})
    if extra:
        for topic, names in extra.items():
            confirmed.setdefault(topic, {fold(topic)}).update(fold(x) for x in names)
            confirmed[topic].add(fold(topic))
            ambiguous.setdefault(topic, [])
    out: dict[str, TopicAliases] = {}
    keys = set(confirmed) | set(ambiguous) | set(clusters)
    for topic in keys:
        conf = set(confirmed.get(topic, {fold(topic)}))
        conf.add(fold(topic))
        out[topic] = TopicAliases(topic=topic, confirmed=frozenset(conf), ambiguous=tuple(ambiguous.get(topic, ())))
    return out


def resolve_topic(topic: str, aliases: dict[str, TopicAliases]) -> TopicAliases:
    key = fold(topic)
    if key in aliases:
        return aliases[key]
    return TopicAliases(topic=key, confirmed=frozenset({key}), ambiguous=())


def _payload(raw: str | None) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def load_snapshot(db_path: str | Path, window: str | Window, cutoff: datetime | None = None) -> Snapshot:
    win = window if isinstance(window, Window) else parse_window(window)
    cut = cutoff or win.end
    if cut.tzinfo is None:
        cut = cut.replace(tzinfo=UTC)
    md5 = db_md5(db_path)
    db = open_ro(db_path)
    try:
        sources = {
            r["id"]: Source(
                source_id=r["id"],
                platform="telegram",
                external_id=str(r["telegram_id"]),
                handle=None,
                role="unknown",
                role_basis="snapshot has no editorial registry",
            )
            for r in db.execute("SELECT id, telegram_id FROM source")
        }
        publications: list[Publication] = []
        comments: list[Publication] = []
        dropped = 0
        handles: dict[int, str | None] = {}
        for r in db.execute("SELECT source_id, external_id, timestamp, payload FROM raw_item"):
            p = _payload(r["payload"])
            ts = parse_ts(p.get("timestamp")) or parse_ts(r["timestamp"])
            handle = p.get("channel_ref")
            if handle:
                handles[r["source_id"]] = handle
            if ts is None:
                continue
            if ts >= cut:
                dropped += 1
                continue
            if not (win.start <= ts < win.end):
                continue
            eid = str(r["external_id"])
            publications.append(
                Publication(
                    pub_id=f"telegram:{r['source_id']}:{eid}",
                    platform="telegram",
                    source_id=r["source_id"],
                    message_external_id=eid,
                    author_id=None,
                    published_at=ts,
                    discovered_at=None,
                    url=p.get("link") or "",
                    text=p.get("text") or "",
                    parent_id=None,
                    thread_id=f"telegram:{r['source_id']}:{eid}",
                    kind="post",
                    has_media=bool(p.get("has_media")),
                    metadata={"channel": handle, "external_id": p.get("external_id", eid)},
                )
            )
        for r in db.execute(
            "SELECT comment_key, source_id, post_id, comment_id, parent_comment_id, ts, text, link, "
            "author_key, has_media FROM comment"
        ):
            ts = parse_ts(r["ts"])
            if ts is None:
                continue
            if ts >= cut:
                dropped += 1
                continue
            if not (win.start <= ts < win.end):
                continue
            pid = str(r["post_id"])
            cid = str(r["comment_id"])
            parent = r["parent_comment_id"]
            comments.append(
                Publication(
                    pub_id=f"telegram:{r['source_id']}:{pid}:c:{cid}",
                    platform="telegram",
                    source_id=r["source_id"],
                    message_external_id=cid,
                    author_id=r["author_key"] or None,
                    published_at=ts,
                    discovered_at=None,
                    url=r["link"] or "",
                    text=r["text"] or "",
                    parent_id=(
                        f"telegram:{r['source_id']}:{pid}:c:{parent}"
                        if parent
                        else f"telegram:{r['source_id']}:{pid}"
                    ),
                    thread_id=f"telegram:{r['source_id']}:{pid}",
                    kind="comment",
                    has_media=bool(r["has_media"]),
                    metadata={
                        "channel": handles.get(r["source_id"]),
                        "post_id": pid,
                        "comment_key": r["comment_key"] or f"{r['source_id']}:{cid}",
                    },
                )
            )
    finally:
        db.close()
    for sid, handle in handles.items():
        if sid in sources:
            sources[sid] = Source(
                source_id=sid,
                platform="telegram",
                external_id=sources[sid].external_id,
                handle=handle,
                role="unknown",
                role_basis=sources[sid].role_basis,
            )
    publications.sort(key=lambda p: (p.published_at, p.pub_id))
    comments.sort(key=lambda p: (p.published_at, p.pub_id))
    return Snapshot(
        window=win,
        cutoff=cut,
        db_md5=md5,
        sources=sources,
        publications=publications,
        comments=comments,
        dropped_after_cutoff=dropped,
    )
